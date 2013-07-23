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
        if self.deferred_endif:
            self.stream.write(self.deferred_endif[1])
            self.deferred_endif = ()

    def put_endif(self):
        if self.deferred_endif:
            self.stream.write(''.join(self.deferred_endif))
            self.deferred_endif = ()

    def start_block(self, tag):
        if tag.name in ('elif', 'else'):
            self.dismiss_endif()
        else:
            self.put_endif()

        self.blocks.append(tag)
        if isinstance(tag, HTMLTag):
            if tag.class_ or tag.id_ or tag.attr:
                self.stream.write('<%s {{ _jade_attr(%r, %r, %r) }}>' %
                                  (tag.name, tag.id_, tag.class_, tag.attr))
            else:
                self.stream.write('<%s>' % tag.name)
        else:
            self.stream.write(maybe_call(control_blocks[tag.name], tag)[0])

    def end_block(self):
        tag = self.blocks.pop()
        if isinstance(tag, HTMLTag):
            self.stream.write('</%s>' % tag.name)
        elif tag.name in ('if', 'elif'):
            self.deferred_endif = [u'{% endif %}', '']
        else:
            self.stream.write(maybe_call(control_blocks[tag.name], tag)[1])

    def literal(self, text):
        self.put_endif()
        if self.blocks and self.blocks[-1].name == u'//-':
            text = filter(lambda x: x == u'\n', text)
        self.stream.write(text)

    def newlines(self, text):
        if self.deferred_endif:
            self.deferred_endif[1] = text
        else:
            self.literal(text)

    def end(self):
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


def default(tag):
    return ('{%% %s %s %%}' % (tag.name, tag.head),
            '{%% end%s %%}' % tag.name)


def single_sided(tag):
    return '{%% %s %s %%}' % (tag.name, tag.head), ''


control_blocks = defaultdict(
    lambda: default,
    {
        '=': ('{{ ', ' }}'),
        '!=': ('{{ ', ' |safe}}'),
        '-': ('{% ', ' %}'),
        '|': ('', ''),
        '//': ('<!--', '-->'),
        '//-': ('', ''),
        'mixin': lambda tag: ('{%% macro %s %%}' % tag.head,
                              '{% endmacro %}'),
        'prepend': lambda tag: ('{%% block %s %%}' % tag.head,
                                '{{ super() }} {% endblock %}'),
        'append': lambda tag: ('{%% block %s %%} {{ super() }}' % tag.head,
                               '{% endblock %}'),
        'extends': single_sided,
        'doctype': lambda tag: (doctypes.get(tag.head or 'default',
                                             '<!DOCTYPE %s>' % tag.head), ''),
        'else': ('{% else %}', '{% endif %}'),
    })


if __name__ == '__main__':
    main(Compiler(stdout))
