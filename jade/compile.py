from sys import stdout
from collections import defaultdict

from .parse import main, HTMLTag


def maybe_call(f, *args, **kwargs):
    if callable(f):
        return f(*args, **kwargs)
    return f


class Compiler(object):
    def __init__(self, stream):
        self.stream = stream
        self.blocks = []
        self.deferred_endif = ()

    def dismiss_endif(self):
        """
        Dismiss an endif, only outputting the newlines.

        The parser doesn't take care of if-elif-else matching.  Instead, it
        will try to close the if block before opening a new elif or else
        block.  Thus the endif block needs to be deferred, along with the
        newlines after it.  When non-empty, self.deferred_endif is a list
        [endif, newlines].
        """
        if self.deferred_endif:
            self.stream.write(self.deferred_endif[1])
            self.deferred_endif = ()

    def put_endif(self):
        """
        Output an endif.
        """
        if self.deferred_endif:
            self.stream.write(''.join(self.deferred_endif))
            self.deferred_endif = ()

    def start_block(self, tag):
        """
        Called by the parser to start a block.  `tag` can be either an HTMLTag
        or a ControlTag.
        """
        if tag.name in ('elif', 'else'):
            self.dismiss_endif()
        else:
            self.put_endif()

        self.blocks.append(tag)
        if isinstance(tag, HTMLTag):
            self.stream.write(u'<%s' % tag.name)
            if 'id' in tag.attr:
                self.stream.write(u' id="{{ %s |escape}}"' %
                                  tag.attr.pop('id'))
            elif tag.id_:
                self.stream.write(u' id="%s"' % tag.id_)

            if 'class' in tag.attr:
                self.stream.write(u' class="%s{{ _jade_class(%s) |escape}}"',
                                  tag.class_ and tag.class_ + u' ' or u'',
                                  tag.attr.pop('class'))
            elif tag.class_:
                self.stream.write(u' class="%s"' % tag.class_)

            for k, v in tag.attr.iteritems():
                self.stream.write(u' %s="{{ %s |escape}}"' % (k, v))

            self.stream.write('>')
        else:
            self.stream.write(maybe_call(control_blocks[tag.name][0], tag))

    def end_block(self):
        """
        Called by the parser to end a block.  The parser doesn't keep track of
        active blocks.
        """
        tag = self.blocks.pop()
        if isinstance(tag, HTMLTag):
            self.stream.write('</%s>' % tag.name)
        elif tag.name in ('if', 'elif'):
            self.deferred_endif = [u'{% endif %}', '']
        else:
            self.stream.write(maybe_call(control_blocks[tag.name][1], tag))

    def literal(self, text):
        """
        Called by the parser to output literal text.  The parser doesn't keep
        track of active blocks.
        """
        self.put_endif()
        self.stream.write(text)

    def newlines(self, text):
        """
        Called by the parser to output newlines that are part of the indent.
        """
        if self.deferred_endif:
            self.deferred_endif[1] = text
        else:
            self.literal(text)

    def end(self):
        """
        Called by the parser to terminate compiling.
        """
        self.put_endif()


doctypes = {
    '5': '<!DOCTYPE html>',
    'default': '<!DOCTYPE html>',
    'xml': '<?xml version="1.0" encoding="utf-8" ?>',
    'transitional': '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 '
                    'Transitional//EN" "http://www.w3.org/TR/xhtml1/'
                    'DTD/xhtml1-transitional.dtd">',
    'strict': '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 '
              'Strict//EN" "http://www.w3.org/TR/xhtml1/'
              'DTD/xhtml1-strict.dtd">',
    'frameset': '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 '
                'Frameset//EN" "http://www.w3.org/TR/xhtml1/'
                'DTD/xhtml1-frameset.dtd">',
    '1.1': '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" '
                '"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">',
    'basic': '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML Basic '
             '1.1//EN" "http://www.w3.org/TR/xhtml-basic/xhtml-basic11.dtd">',
    'mobile': '<!DOCTYPE html PUBLIC "-//WAPFORUM//DTD XHTML Mobile 1.2//EN" '
              '"http://www.openmobilealliance.org/tech/DTD/'
              'xhtml-mobile12.dtd">'
}


def default_start(tag):
    return '{%% %s %s %%}' % (tag.name, tag.head)


def default_end(tag):
    return '{%% end%s %%}' % tag.name


def doctype(tag):
    return doctypes.get(tag.head.lower() or 'default',
                        '<!DOCTYPE %s>' % tag.head)


control_blocks = defaultdict(
    lambda: (default_start, default_end),
    {
        '=':       ('{{ ', ' }}'),
        '!=':      ('{{ ', ' |safe}}'),
        '-':       ('{% ', ' %}'),
        '|':       ('', ''),
        '//':      ('<!--', '-->'),
        '//-':     ('{#', '#}'),
        ':':       (lambda tag: '{%% filter %s %%}' % tag.head,
                    '{% endfilter %}'),
        'mixin':   (lambda tag: '{%% macro %s %%}' % tag.head,
                    '{% endmacro %}'),
        'prepend': (lambda tag: '{%% block %s %%}' % tag.head,
                    '{{ super() }} {% endblock %}'),
        'append':  (lambda tag: '{%% block %s %%} {{ super() }}' % tag.head,
                    '{% endblock %}'),
        'extends': (default_start, ''),
        'doctype': (doctype, ''),
        'else':    ('{% else %}', '{% endif %}'),
    })


if __name__ == '__main__':
    main(Compiler(stdout))
