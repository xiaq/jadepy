jade.py
=======

Another Python implementation of the [jade templating language](https://github.com/visionmedia/jade).

Feature
-------

* Line-to-line conversion to minimalize debug headaches

Conformity
----------

The goal is to achieve identical behavior for most examples listed on the
[official README](https://github.com/visionmedia/jade/blob/master/Readme.md),
except

* deprecated features
* examples with Javascript code lines
* when certain features conflict with Jinja2 features the latter would usually
  take precedence

Relevant examples have been extracted and revised and can be found in the
`conformity-tests/` subdirectory.  All omissions and revisions are documented
in individual files there.

Usage
-----

Before I have done proper packaging, use this for testing:

    python -m jade.compile < some.jade

The output is Jinja2.

License
-------

MIT license, same as official Jade.  See LICENSE for a copy.
