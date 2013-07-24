def has_proper_prefix(s, prefix):
    return len(s) > len(prefix) and s.startswith(prefix)


def repr_calling(args, kwargs):
    """
    Reconstruct function calling code.
    """
    li = []
    li.extend(repr(a) for a in args)
    li.extend('%s=%r' % (k, v) for k, v in kwargs.items())
    return ', '.join(li)


def find_all(s, sub):
    """
    Find all occurences of `sub` in `s`.
    """
    i = 0
    while True:
        i = s.find(sub, i)
        if i == -1:
            return
        yield i
        i += 1
