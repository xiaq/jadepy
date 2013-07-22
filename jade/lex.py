import string

from sys import stdin
from functools import wraps
from collections import namedtuple


Token = namedtuple('Token', 'type info text')


class LexError(Exception):
    pass


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

    def __call__(self):
        state = self.init_state
        while state is not None:
            token, state = state()
            if token is not None:
                yield token

    def error(self, msg, cls=LexError):
        # TODO inject current line & column number
        return cls(msg)

    def off_end(self):
        return self.pos >= len(self.text)

    def conclude(self, t, omitempty=True, **info):
        text = self.text[self.start:self.pos]
        self.start = self.pos
        return Token(t, info, text) if text or not omitempty else None

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

    def expect(self, *valids):
        rune = self.accept(*valids)
        if not rune:
            raise self.error('Expect one of %r' % valids)
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


def has_proper_prefix(s, prefix):
    return len(s) > len(prefix) and s.startswith(prefix)


def allow_eof(f):
    @wraps(f)
    def g(self):
        if self.off_end():
            return None, None
        return f(self)
    return g


def skip_inline_whitespace(f):
    @wraps(f)
    def g(self):
        self._drop_inline_whitespace()
        return f(self)
    return g


WHITESPACE = intern('whitespace')
INDENT = intern('indent')
TAG = intern('tag')
VERBATIM = intern('verbatim')
TEXT = intern('text')
DOT = intern('dot')
HASH = intern('hash')
LPAREN = intern('lparen')
KEY = intern('key')
EQUAL = intern('equal')
EXPR = intern('expr')
COMMA = intern('comma')
RPAREN = intern('rparen')
TAG_CONCLUDER = intern('tag_concluder')


class Lexer(AbstractLexer):
    """
    A jade lexer.
    """
    valid_in_tags = string.letters
    valid_in_keys = string.letters + '-:'
    valid_in_qualifiers = string.letters + '-_'
    inline_whitespace = ' \t'

    def __init__(self, text):
        super(Lexer, self).__init__(text, self.tag)
        self.indent_levels = [u'']

    def _accept_inline_whitespace(self):
        return self.accept_run(self.inline_whitespace)

    def _accept_indent_text(self):
        self.require(u'\n')
        return self._accept_inline_whitespace()

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
        An indentation (INDENT).

        An empty line is tokenized as WHITESPACE instead of INDENT, so that it
        doesn't break the flow of indentation.

        The preceding newline is considered part of the indentation.  This
        makes it trivial to put closing tags on the last line of a block
        instead of the first line of the next block, e.g.:

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
        text = self._accept_indent_text()

        if text == u'' and self.peek() in u'\n':
            return self.conclude(WHITESPACE), self.indent
        elif text == self.indent_levels[-1]:
            # Indent unchanged
            off = 0
        elif text.startswith(self.indent_levels[-1]):
            # Indent level increase
            self.indent_levels.append(text)
            off = 1
        else:
            # Indent level decrease - find out how many levels are dropped
            i = -1
            while has_proper_prefix(self.indent_levels[i-1], text):
                i -= 1
            if self.indent_levels[i-1] != text:
                raise self.error('Bad indentation')
            self.indent_levels = self.indent_levels[:i]
            off = i

        return self.conclude(INDENT, off=off), self.tag

    @allow_eof
    def tag(self):
        """
        A tag name (TAG).

        A few special tags lead a verbatim block.  Other tags takes optional
        tag qualifiers with *no* separating whitespace, followed by an
        optional tag concluder.

        A <div> tag may be ommitted when followed by at least one qualifier.
        """
        # verbatim block leader
        if self.accept('//-', '//', '-', '=', '!='):
            return self.conclude(TAG), self.verbatim
        # tags that accept no qualifier
        elif self.accept('|', '!!!', 'doctype'):
            return self.conclude(TAG), self.line
        # an ordinary tag
        elif self.accept_run(self.valid_in_tags):
            return self.conclude(TAG), self.maybe_qualifier
        # an implicit <div> tag
        elif self.peek() in u'.#(':
            return self.conclude(TAG, omitempty=False), self.qualifier
        else:
            raise self.error('No valid tag found')

    def verbatim(self):
        """
        A verbatim block (VERBATIM) is introduced by one of the special tags
        listed in :func:`tag`, and spans into subsequent lines as long as
        their indentations have that of the first line as a proper prefix.
        The indentation is not subject to the usual rule.  Example:

            //- a comment
             block
                foo
              bar
            p ends here
        """
        self._advance_line()
        while True:
            indent = self._accept_indent_text()
            if not has_proper_prefix(indent, self.indent_levels[-1]):
                # Back up the indent *plus* the newline
                self.backup(len(indent) + 1)
                return self.conclude(VERBATIM), self.indent
            self._advance_line()

    @allow_eof
    def maybe_qualifier(self):
        if self.peek() in u'.#(':
            return self.qualifier()
        else:
            return self.maybe_tag_concluder()

    def qualifier(self):
        """
        A qualifier can be either of class qualifier introduced by DOT, id
        qualifier introduced by HASH, or a attribute list introduced by
        LPAREN.
        """
        rune = self.require(u'.', u'#', u'(')
        if rune in u'.#':
            return (self.conclude({u'.': DOT, u'#': HASH}[rune]),
                    self.qualifier_arg)
        else:
            return self.conclude(LPAREN), self.maybe_attr_key

    def qualifier_arg(self):
        self.accept_run(self.valid_in_qualifiers)
        return self.conclude(TEXT), self.maybe_qualifier

    @skip_inline_whitespace
    def maybe_attr_key(self):
        """
        A key in the attribute list, as a KEY token.
        """
        if self.peek() == u')':
            return None, self.rparen
        self.accept_run(self.valid_in_keys)
        return self.conclude(KEY), self.maybe_equal

    @skip_inline_whitespace
    def maybe_equal(self):
        """
        The equal sign (EQUAL) introduces value for an attribute.  If the
        equal sign and value are ommitted, it defaults to the same as the
        attribute name.
        """
        if self.accept(u'='):
            return self.conclude(EQUAL), self.expr
        else:
            rune = self.peek()
            if rune == u',':
                return None, self.comma
            elif rune == u')':
                return None, self.rparen
            else:
                raise self.error('Bad character after attribute key')

    @skip_inline_whitespace
    def expr(self):
        """
        A Python expression (EXPR) in the attribute list.

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
                self.backup()
                return (self.conclude(EXPR),
                        self.comma if rune == ',' else self.rparen)
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

    @skip_inline_whitespace
    def comma(self):
        """
        The comma (COMMA) concludes an attribute in the attribute list.  The
        last attribute may have its comma omitted.
        """
        self.require(u',')
        return self.conclude(COMMA), self.maybe_attr_key

    @skip_inline_whitespace
    def rparen(self):
        """
        The closing parenthesis (RPAREN) concludes an attribute list.
        """
        self.require(u')')
        return self.conclude(RPAREN), self.maybe_qualifier

    def maybe_tag_concluder(self):
        """
        A tag concluder (TAG_CONCLUDER) follows a tag or its qualifier
        immediately and determines the environment after the tag:

        * A colon introduces another tag that is the sole child of the
          former tag;

        * An equal sign introduces a verbatim block that is interpreted as a
          Python expression;

        * A dot introduces a verbatim block that is output as is;

        * Lack of a tag concluder leaves the rest of the line output as is.
        """
        if self.accept(u':'):
            token = self.conclude(TAG_CONCLUDER)
            if self.accept_run(self.inline_whitespace):
                self.drop()
            return token, self.tag
        elif self.accept(u'=', u'.'):
            return self.conclude(TAG_CONCLUDER), self.verbatim
        else:
            return None, self.line

    @skip_inline_whitespace
    def line(self):
        """
        The rest of the line as a single TEXT token.
        """
        eol = self._advance_line()
        return self.conclude(TEXT), self.indent if eol == '\n' else None


def main():
    text = stdin.read().decode('utf8')
    lexer = Lexer(text)
    for token in lexer():
        print token


if __name__ == '__main__':
    main()
