# -*- coding: utf8 -*-
"""
    kaptan
    ~~~~~~

    configuration parser.

    :copyright: (c) 2013 by the authors and contributors (See AUTHORS file).
    :license: BSD, see LICENSE for more details.
"""

from __future__ import print_function, unicode_literals

import argparse
import os
from collections import Mapping, Sequence

from .handlers.dict_handler import DictHandler
from .handlers.pyfile_handler import PyFileHandler
from .handlers.ini_handler import IniHandler
from .handlers.json_handler import JsonHandler
from .handlers.yaml_handler import YamlHandler

SENTINEL = object()

HANDLER_EXT = {
    'ini': 'ini',
    'conf': 'ini',
    'yaml': 'yaml',
    'yml': 'yaml',
    'json': 'json',
    'py': 'file',
}


class Kaptan(object):

    HANDLER_MAP = {
        'json': JsonHandler,
        'dict': DictHandler,
        'yaml': YamlHandler,
        'file': PyFileHandler,
        'ini': IniHandler,
    }

    def __init__(self, handler=None):
        self.configuration_data = dict()
        self.handler = None
        if handler:
            self.handler = self.HANDLER_MAP[handler]()

    def upsert(self, key, value):
        self.configuration_data.update({key: value})
        return self

    def _is_python_file(self, value):
        """ Return True if the `value` is the path to an existing file with a
        `.py` extension. False otherwise
        """
        ext = os.path.splitext(value)[1][1:]
        if ext == 'py' or os.path.isfile(value + '.py'):
            return True
        return False

    def import_config(self, value):
        if isinstance(value, dict):  # load python dict
            self.handler = self.HANDLER_MAP['dict']()
            data = value
        elif os.path.isfile(value) and not self._is_python_file(value):
            if not self.handler:
                try:
                    key = HANDLER_EXT.get(os.path.splitext(value)[1][1:], None)
                    self.handler = self.HANDLER_MAP[key]()
                except:
                    raise RuntimeError("Unable to determine handler")
            with open(value) as f:
                data = f.read()
        elif self._is_python_file(value): # is a python file
            self.handler = self.HANDLER_MAP[HANDLER_EXT['py']]()
            if not value.endswith('.py'):
                value += '.py' # in case someone is refering to a module
            data = os.path.abspath(os.path.expanduser(value))
            if not os.path.isfile(data):
                raise IOError('File {0} not found.'.format(data))
        else:
            if not self.handler:
                raise RuntimeError("Unable to determine handler")

            data = value

        self.configuration_data = self.handler.load(data)
        return self

    def _get(self, key):
        current_data = self.configuration_data

        for chunk in key.split('.'):
            if isinstance(current_data, Mapping):
                current_data = current_data[chunk]
            elif isinstance(current_data, Sequence):
                chunk = int(chunk)

                current_data = current_data[chunk]
            else:
                # A scalar type has been found
                return current_data

        return current_data

    def get(self, key=None, default=SENTINEL):
        if not key:  # .get() or .get(''), return full config
            return self.export('dict')

        try:
            try:
                return self._get(key)
            except KeyError:
                raise KeyError(key)
            except ValueError:
                raise ValueError("Sequence index not an integer")
            except IndexError:
                raise IndexError("Sequence index out of range")
        except (KeyError, ValueError, IndexError):
            if default is not SENTINEL:
                return default
            raise

    def add(self, key, value=None, replace=False):
        current_data = self.configuration_data
        keys = key.split('.')
        new_key = keys[0]
        is_key_exist = False
        if len(keys) > 1:
            new_key = keys.pop()
            for chunk in keys:
                try:
                    if not replace and new_key in current_data[chunk]:
                        is_key_exist = True
                    current_data = current_data[chunk]
                except KeyError:
                    current_data[chunk] = {}
                    current_data = current_data[chunk]
        try:
            if replace:
                current_data[new_key] = value
            elif isinstance(current_data[new_key], list):
                current_data[new_key].append(value)
            elif is_key_exist:
                raise RuntimeError("Key %s already exist" % new_key)
        except KeyError as e:
            current_data[new_key] = value

        return self

    def remove(self, key, index=None):
        current_data = self.configuration_data
        keys = key.split('.')
        exact_key = keys[0]
        if len(keys) > 1:
            exact_key = keys.pop()
        for chunk in keys:
            current_data = current_data[chunk]
        if isinstance(index, int) and isinstance(current_data[exact_key], list):
            current_data[exact_key].pop(index)
        else:
            del current_data[exact_key]

        return self

    def export(self, handler=None, **kwargs):
        if not handler:
            handler_class = self.handler
        else:
            handler_class = self.HANDLER_MAP[handler]()

        return handler_class.dump(self.configuration_data, **kwargs)

    def __handle_default_value(self, key, default):
        if default == SENTINEL:
            raise KeyError(key)
        return default


def get_parser():
    """Create and return argument parser.

    :rtype: :class:`argparse.ArgumentParser`
    :return: CLI Parser
    """
    parser = argparse.ArgumentParser(
        prog=__package__,
        description='Configuration manager in your pocket'
    )
    parser.add_argument('config_file', action='store', nargs='*',
                    help="file/s to load config from")
    parser.add_argument('--handler', action='store', default='json',
                    help="set default handler")
    parser.add_argument('-e', '--export', action='store', default='json',
                    help="set format to export to")
    parser.add_argument('-k', '--key', action='store',
                    help="set config key to get value of")
    return parser

def main():
    from sys import stdin
    from collections import OrderedDict

    parser = get_parser()
    args, ukargs = parser.parse_known_args()

    config = Kaptan()
    config_files = args.config_file + ukargs

    if not config_files:
        parser.print_help()
        parser.exit(1)

    def get_handlers():
        for f in config_files:
            s = f.split(':')
            if len(s) != 2:
                s += [None]
            yield tuple(s)

    config_handlers = OrderedDict(list(get_handlers()))

    for config_file, handler in config_handlers.items():
        is_stdin = config_file == '-'
        if is_stdin:
            handler = handler or args.handler
        else:
            ext = handler or os.path.splitext(config_file)[1][1:]
            handler = HANDLER_EXT.get(ext, args.handler)
        _config = Kaptan(handler=handler)
        if is_stdin:
            _config.import_config(stdin.read())
        else:
            with open(config_file) as f:
                _config.import_config(f.read())
        config.configuration_data.update(_config.configuration_data)

    if args.key:
        print(config.get(args.key))
    else:
        print(config.export(args.export))

    parser.exit(0)
