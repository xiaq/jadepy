from sys import stdout
from collections import defaultdict

from .parse import main, HTMLTag


def maybe_call(f, *args, **kwargs):
    if callable(f):
        return f(*args, **kwargs)
    return f


class Compiler(object):
    def __init__(self):
        self.blocks = []

    def start_block(self, tag):
        self.blocks.append(tag)
        if isinstance(tag, HTMLTag):
            if tag.class_ or tag.id_ or tag.attr:
                stdout.write('<%s {{ _jade_attr(%r, %r, %r) }}>' %
                             (tag.name, tag.id_, tag.class_, tag.attr))
            else:
                stdout.write('<%s>' % tag.name)
        else:
            stdout.write(maybe_call(control_blocks[tag.name], tag)[0])

    def end_block(self):
        tag = self.blocks.pop()
        if isinstance(tag, HTMLTag):
            stdout.write('</%s>' % tag.name)
        else:
            stdout.write(maybe_call(control_blocks[tag.name], tag)[1])

    def literal(self, text):
        if self.blocks and self.blocks[-1].name == u'//-':
            text = filter(lambda x: x == u'\n', text)
        stdout.write(text)


doctypes = {
    '5': '<!DOCTYPE html>',
    'default': '<!DOCTYPE html>',
    'xml': '<?xml version="1.0" encoding="utf-8" ?>',
    'transitional': '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">',
    'strict': '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">',
    'frameset': '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Frameset//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-frameset.dtd">',
    '1.1': '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">',
    'basic': '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML Basic 1.1//EN" "http://www.w3.org/TR/xhtml-basic/xhtml-basic11.dtd">',
    'mobile': '<!DOCTYPE html PUBLIC "-//WAPFORUM//DTD XHTML Mobile 1.2//EN" "http://www.openmobilealliance.org/tech/DTD/xhtml-mobile12.dtd">'
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
    })


if __name__ == '__main__':
    main(Compiler)
