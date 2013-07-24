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
