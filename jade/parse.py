import string

from sys import stdin
from functools import wraps
from bisect import bisect_left

from .utils import has_proper_prefix, repr_calling, find_all


class LexError(Exception):
    def __init__(self, msg, pos, line):
        super(LexError, self).__init__(msg, pos, line)
        self.msg = msg
        self.pos = pos
        self.line = line

    def pprint(self):
        lineno, colno = self.pos
        indicator = ' ' * (colno - 1) + '^'
        return """\
{err_start}{name}: {msg}{err_end} around line {lineno}, column {colno}:
    {line}
    {indicator}""".format(
        err_start='\033[31;1m', err_end='\033[m',
        name=self.__class__.__name__, msg=self.msg,
        lineno=lineno, colno=colno,
        line=self.line, indicator=indicator)


class LexerBug(LexError):
    pass


class AbstractLexer(object):
    """
    A lexer keeps the state of lex parsing.

    This is the abstract class that provides helpers but define no states.
    """

    def __init__(self, text, init_state=None):
        self.text = text

        self.pos = self.start = 0
        self.init_state = init_state
        self.newline_pos = ([-1] + list(find_all(self.text, '\n')) +
                            [len(self.text)])

    def __call__(self):
        state = self.init_state
        while state is not None:
            if self.start != self.pos:
                raise LexerBug('State starts with inconsistent state')
            state = state()

    def error(self, msg, cls=LexError):
        lineno = bisect_left(self.newline_pos, self.start)
        last_newline = self.newline_pos[lineno - 1]
        colno = self.pos - last_newline
        line = self.text[last_newline + 1:self.newline_pos[lineno]]
        return cls(msg, (lineno, colno), line)

    def off_end(self):
        return self.pos >= len(self.text)

    def conclude(self):
        text = self.text[self.start:self.pos]
        self.start = self.pos
        return text

    def drop(self):
        self.start = self.pos

    def peek(self, n=1):
        return self.text[self.pos:self.pos+n]

    def advance(self, n=1):
        text = self.peek(n)
        self.pos += n
        return text

    def backup(self, n=1):
        self.pos -= n

    def rollback(self):
        self.pos = self.start

    def accept(self, *valids):
        for v in valids:
            if self.peek(len(v)) == v:
                self.advance(len(v))
                return v
        return u''

    def require(self, *valids):
        rune = self.accept(*valids)
        if not rune:
            raise self.error('Require one of %r' % valids, cls=LexerBug)
        return rune

    def accept_run(self, valid):
        if not callable(valid):
            valids = list(valid)
            valid = lambda x: x in valids
        start = self.pos
        while valid(self.advance()):
            pass
        self.backup()
        return self.text[start:self.pos]


def allow_eof(f):
    @wraps(f)
    def g(self):
        if self.off_end():
            return self.end
        return f(self)
    return g


def skip_inline_whitespace(f):
    @wraps(f)
    def g(self):
        self._drop_inline_whitespace()
        return f(self)
    return g


class HTMLTag(object):
    def __init__(self, name, class_=None, id_=None, attr=None):
        self.name = name
        self.class_ = class_
        self.id_ = id_
        self.attr = attr or {}

    def __repr__(self):
        return 'HTMLTag(%r, class_=%r, id_=%r, attr=%r)' % (
            self.name, self.class_, self.id_, self.attr)


class ControlTag(object):
    def __init__(self, name, head=None):
        self.name = name
        self.head = head

    def __repr__(self):
        return 'ControlTag(%r, head=%r)' % (self.name, self.head)


control_tag_aliases = {
    'else if': 'elif', '!!!': 'doctype', 'each': 'for',
    'block append': 'append', 'block prepend': 'prepend',
}

control_tags = control_tag_aliases.keys() + [
    '//',
    'doctype', 'extends',
    'if', 'elif', 'else', 'for',
    'block', 'append', 'prepend'
]


class Parser(AbstractLexer):
    """
    A jade lexer and parser in one.
    """
    valid_in_tags = string.letters + string.digits
    valid_in_keys = string.letters + '-:'
    valid_in_idents = string.letters + string.digits + '-_'
    inline_whitespace = ' \t'

    def __init__(self, text, compiler):
        super(Parser, self).__init__(text, self.tag)
        self.compiler = compiler
        self.indent_levels = [u'']
        self.indented_blocks = [0]

    def _accept_inline_whitespace(self):
        return self.accept_run(self.inline_whitespace)

    def _accept_ident(self):
        return self.accept_run(self.valid_in_idents)

    def _advance_line(self):
        while True:
            rune = self.advance()
            if rune in ('', '\n'):
                self.backup()
                return rune

    def _drop_inline_whitespace(self):
        self.accept_run(self.inline_whitespace)
        self.drop()

    # States
    @allow_eof
    def indent(self):
        """
        An indentation is a series of newlines followed by inline whitespaces.

        Having preceding newline as part of the indentation makes it trivial
        to put closing tags on the last line of a block instead of the first
        line of the next block, e.g.:

            div
                p
            span

        should be transformed into into

            <div>
                <p></p></div>
            <span></span>

        instead of

            <div>
                <p>
            </p></div><span></span>
        """
        newlines = self.accept_run(u'\n')
        text = self._accept_inline_whitespace()
        self.drop()

        if has_proper_prefix(text, self.indent_levels[-1]):
            # Indent level increase
            self.indent_levels.append(text)
            self.indented_blocks.append(0)
        else:
            # Indent level unchanged or decrease - find out how many
            # blocks need to be closed
            i = -1
            blocks_to_close = 0
            while True:
                blocks_to_close += self.indented_blocks[i]
                if not has_proper_prefix(self.indent_levels[i], text):
                    break
                i -= 1
            if self.indent_levels[i] != text:
                raise self.error('Bad indentation')
            if i < -1:
                self.indent_levels[i+1:] = []
            self.indented_blocks[i:] = [0]
            for k in range(0, blocks_to_close):
                self.compiler.end_block()

        self.compiler.newlines(newlines)
        return self.tag

    @allow_eof
    def tag(self):
        """
        A tag name.

        A few special tags always lead a verbatim block.  Other tags takes
        optional tag qualifiers and an optional tag concluder.  Tag qualifiers
        and concluders must not have leading whitespaces.

        The environment after the tag is determined by the tag concluder.

        A <div> tag may be ommitted when followed by at least one qualifier.
        """
        self.indented_blocks[-1] += 1

        # verbatim block leader
        if self.accept('//-', '-', '=', '!='):
            self.compiler.start_block(ControlTag(self.conclude()))
            return self.verbatim

        # filter block
        if self.accept(':'):
            # XXX Filter name uses same alphabet as tag name; may not be
            # appropriate
            if self.accept_run(self.valid_in_tags):
                self.compiler.start_block(ControlTag(':', self.conclude()[1:]))
                return self.verbatim
            else:
                self.rollback()

        # pipe accepts no qualifier, but is otherwise an ordinary tag
        if self.accept('|'):
            self.drop()
            self.compiler.start_block(ControlTag('|'))
            return self.single_line_literal

        # "control tags" accept no qualifier *and* should have the following
        # text as part of the tag, stored in its `head` attribute
        name = self.accept(*control_tags)
        if name:
            terminator = self.peek()
            # alphanumerical tags need a non-alphanumerical terminator
            if (name[-1] in self.valid_in_tags and
                    terminator and terminator in self.valid_in_tags):
                self.rollback()
            else:
                try:
                    name = control_tag_aliases[name]
                except KeyError:
                    pass
                self._drop_inline_whitespace()
                self._advance_line()
                self.compiler.start_block(
                    ControlTag(name, head=self.conclude()))
                return self.indent

        # an ordinary HTML tag
        if self.accept_run(self.valid_in_tags):
            self.this_tag = HTMLTag(self.conclude())
            return self.maybe_qualifier

        # an implicit <div> tag
        if self.peek() in u'.#(':
            self.this_tag = HTMLTag(u'div')
            return self.qualifier

        raise self.error('No valid tag found')

    @skip_inline_whitespace
    def verbatim(self):
        """
        A verbatim block is introduced by one of the special tags listed in
        :func:`tag`, and spans into subsequent lines as long as their
        indentations have that of the first line as a proper prefix.  The
        indentation is not subject to the usual rule.  Example:

            //- a comment
             block
                foo
              bar
            p ends here
        """
        self._advance_line()
        while True:
            self.accept_run(u'\n')
            indent = self._accept_inline_whitespace()
            if not has_proper_prefix(indent, self.indent_levels[-1]):
                # Back up the indent *plus* the newline
                self.backup(len(indent) + 1)
                self.compiler.literal(self.conclude())
                return self.indent
            self._advance_line()

    @allow_eof
    def maybe_qualifier(self):
        rune = self.peek()
        if rune in u'#(':
            return self.qualifier
        elif rune == u'.':
            runes = self.peek(2)
            if len(runes) == 2 and runes[1] in self.valid_in_idents:
                return self.qualifier
            else:
                return self.maybe_tag_concluder
        else:
            return self.maybe_tag_concluder

    def qualifier(self):
        """
        A qualifier can be either of class specifier introduced by dot, id
        specifier introduced by dot, or a attribute list introduced by an
        opening parenthesis.
        """
        rune = self.require(u'.', u'#', u'(')
        self.drop()
        if rune == u'#':
            if not self._accept_ident():
                raise self.error('No valid id found')
            self.this_tag.id_ = self.conclude()
            return self.maybe_qualifier
        elif rune == u'.':
            # There must be a valid ident here, otherwise it would be
            # interpreted as a tag concluder
            self._accept_ident()
            self.this_tag.class_ = self.conclude()
            return self.maybe_qualifier
        else:
            return self.maybe_attr_key

    @skip_inline_whitespace
    def maybe_attr_key(self):
        """
        A key in the attribute list.
        """
        if self.peek() == u')':
            self.drop()
            return self.maybe_qualifier
        if not self.accept_run(self.valid_in_keys):
            raise self.error('No valid attribute key found')
        self.this_tag_attr_key = self.conclude()
        return self.after_attr_key

    @skip_inline_whitespace
    def after_attr_key(self):
        """
        After the attribute key might be an equal sign, which introduces the
        value for the attribute; or a comma that concludes current attribute;
        or a closing parenthesis that concludes the whole attribute list.

        The value of an attribute, when unspecified, defaults to the same as
        the attribute name.
        """
        rune = self.advance()
        self.drop()
        if rune == u'=':
            return self.expr
        elif rune == u',':
            return self.maybe_attr_key
        elif rune == u')':
            return self.maybe_qualifier
        else:
            raise self.error('Bad character after attribute key')

    @skip_inline_whitespace
    def expr(self):
        """
        A Python expression in the attribute list.

        Tokenizing a Python expression requires a little work, since it is
        terminated with either a comma, which may appear inside [] {} or (),
        or a closing parenthesis, which may be closing another level of (
        introduced in the Python expression.  Also, both can appear in string
        literals.
        """
        opener_of = {u')': u'(', u']': u'[', u'}': u'{'}
        openers = opener_of.values()
        closers = opener_of.keys()

        quote = None
        enclose = []

        while True:
            rune = self.advance()
            if not rune:
                raise self.error('Unterminated Python expression')
            if quote:
                if rune == quote:
                    quote = None
                elif rune == '\\':
                    if not self.advance():
                        raise self.error('Unterminated string literal')
            elif rune in u',)' and not enclose:
                self.this_tag.attr[self.this_tag_attr_key] = (
                    self.conclude()[:-1])  # drop trailing , or )
                return (self.maybe_attr_key if rune == ',' else
                        self.maybe_qualifier)
            elif rune in u'"\'':
                quote = rune
            elif rune in openers:
                enclose.append(rune)
            elif rune in closers:
                opener = opener_of[rune]
                if not enclose:
                    raise self.error('No opening %r to close' % opener)
                elif enclose[-1] != opener:
                    raise self.error(
                        "Closing %r doesn't match opening" % (rune, opener))
                else:
                    enclose.pop()

    def maybe_tag_concluder(self):
        """
        A tag concluder follows a tag or its qualifier immediately and
        determines the environment after the tag:

        * A colon introduces another tag that is the sole child of the
          former tag;

        * An equal sign introduces a verbatim block that is interpreted as a
          Python expression.  It is equivalent to ':=';

        * A dot introduces a verbatim block that is output as is;

        * Lack of a tag concluder leaves the rest of the line output as is.
        """
        self.compiler.start_block(self.this_tag)
        if self.accept(u':'):
            self.drop()
            self._drop_inline_whitespace()
            return self.tag
        elif self.accept(u'!=', u'='):
            self.backup()
            return self.tag
        elif self.accept(u'.'):
            self.verbatim_leader = self.conclude()
            return self.verbatim
        else:
            return self.single_line_literal

    def single_line_literal(self):
        self._drop_inline_whitespace()
        self._advance_line()
        text = self.conclude()
        if text:
            self.compiler.literal(text)
        return self.indent

    def end(self):
        self.compiler.end()
        return None


class DummyCompiler(object):
    def __getattr__(self, name):
        def f(*args, **kwargs):
            print '%s(%s)' % (name, repr_calling(args, kwargs))
        return f


def main(compiler):
    text = stdin.read().decode('utf8')
    parser = Parser(text, compiler)
    try:
        parser()
    except LexError as e:
        print e.pprint()


if __name__ == '__main__':
    main(DummyCompiler())
