# -*- coding: utf-8 -*-
import collections
import os
import tempfile
import unittest


from django.conf import settings
from django.core.cache import cache
from django.core.validators import ValidationError
from django.utils import translation

import mock
from nose.tools import assert_raises, eq_, ok_, raises

import amo
from amo.utils import (attach_trans_dict, cache_ns_key, escape_all,
                       find_language, LocalFileStorage, no_translation,
                       resize_image, rm_local_tmp_dir, slugify, slug_validator,
                       to_language)
from mkt.webapps.models import Addon


u = u'Ελληνικά'


def test_slug_validator():
    eq_(slug_validator(u.lower()), None)
    eq_(slug_validator('-'.join([u.lower(), u.lower()])), None)
    assert_raises(ValidationError, slug_validator, '234.add')
    assert_raises(ValidationError, slug_validator, 'a a a')
    assert_raises(ValidationError, slug_validator, 'tags/')


def test_slugify():
    x = '-'.join([u, u])
    y = ' - '.join([u, u])

    def check(x, y):
        eq_(slugify(x), y)
        slug_validator(slugify(x))
    s = [
        ('xx x  - "#$@ x', 'xx-x-x'),
        (u'Bän...g (bang)', u'bäng-bang'),
        (u, u.lower()),
        (x, x.lower()),
        (y, x.lower()),
        ('    a ', 'a'),
        ('tags/', 'tags'),
        ('holy_wars', 'holy_wars'),
        # I don't really care what slugify returns. Just don't crash.
        (u'x荿', u'x\u837f'),
        (u'ϧ΃蒬蓣', u'\u03e7\u84ac\u84e3'),
        (u'¿x', u'x'),
    ]
    for val, expected in s:
        yield check, val, expected


def test_resize_image():
    # src and dst shouldn't be the same.
    assert_raises(Exception, resize_image, 't', 't', 'z')


def test_resize_transparency():
    src = os.path.join(settings.ROOT, 'apps', 'amo', 'tests',
                       'images', 'transparent.png')
    dest = tempfile.mkstemp(dir=settings.TMP_PATH)[1]
    expected = src.replace('.png', '-expected.png')
    try:
        resize_image(src, dest, (32, 32), remove_src=False, locally=True)
        with open(dest) as dfh:
            with open(expected) as efh:
                assert dfh.read() == efh.read()
    finally:
        if os.path.exists(dest):
            os.remove(dest)


def test_to_language():
    tests = (('en-us', 'en-US'),
             ('en_US', 'en-US'),
             ('en_us', 'en-US'),
             ('FR', 'fr'),
             ('el', 'el'))

    def check(a, b):
        eq_(to_language(a), b)
    for a, b in tests:
        yield check, a, b


def test_find_language():
    tests = (('en-us', 'en-US'),
             ('en_US', 'en-US'),
             ('en', 'en-US'),
             ('cy', 'cy'),  # A hidden language.
             ('FR', 'fr'),
             ('es-ES', None),  # We don't go from specific to generic.
             ('xxx', None))

    def check(a, b):
        eq_(find_language(a), b)
    for a, b in tests:
        yield check, a, b


def test_no_translation():
    """
    `no_translation` provides a context where only the default
    language is active.
    """
    lang = translation.get_language()
    translation.activate('pt-br')
    with no_translation():
        eq_(translation.get_language(), settings.LANGUAGE_CODE)
    eq_(translation.get_language(), 'pt-br')
    with no_translation('es'):
        eq_(translation.get_language(), 'es')
    eq_(translation.get_language(), 'pt-br')
    translation.activate(lang)


class TestLocalFileStorage(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.stor = LocalFileStorage()

    def tearDown(self):
        rm_local_tmp_dir(self.tmp)

    def test_read_write(self):
        fn = os.path.join(self.tmp, 'somefile.txt')
        with self.stor.open(fn, 'w') as fd:
            fd.write('stuff')
        with self.stor.open(fn, 'r') as fd:
            eq_(fd.read(), 'stuff')

    def test_non_ascii_filename(self):
        fn = os.path.join(self.tmp, u'Ivan Krsti\u0107.txt')
        with self.stor.open(fn, 'w') as fd:
            fd.write('stuff')
        with self.stor.open(fn, 'r') as fd:
            eq_(fd.read(), 'stuff')

    def test_non_ascii_content(self):
        fn = os.path.join(self.tmp, 'somefile.txt')
        with self.stor.open(fn, 'w') as fd:
            fd.write(u'Ivan Krsti\u0107.txt'.encode('utf8'))
        with self.stor.open(fn, 'r') as fd:
            eq_(fd.read().decode('utf8'), u'Ivan Krsti\u0107.txt')

    def test_make_file_dirs(self):
        dp = os.path.join(self.tmp, 'path', 'to')
        self.stor.open(os.path.join(dp, 'file.txt'), 'w').close()
        assert os.path.exists(self.stor.path(dp)), (
            'Directory not created: %r' % dp)

    def test_do_not_make_file_dirs_when_reading(self):
        fpath = os.path.join(self.tmp, 'file.txt')
        with open(fpath, 'w') as fp:
            fp.write('content')
        # Make sure this doesn't raise an exception.
        self.stor.open(fpath, 'r').close()

    def test_make_dirs_only_once(self):
        dp = os.path.join(self.tmp, 'path', 'to')
        with self.stor.open(os.path.join(dp, 'file.txt'), 'w') as fd:
            fd.write('stuff')
        # Make sure it doesn't try to make the dir twice
        with self.stor.open(os.path.join(dp, 'file.txt'), 'w') as fd:
            fd.write('stuff')
        with self.stor.open(os.path.join(dp, 'file.txt'), 'r') as fd:
            eq_(fd.read(), 'stuff')

    def test_delete_empty_dir(self):
        dp = os.path.join(self.tmp, 'path')
        os.mkdir(dp)
        self.stor.delete(dp)
        eq_(os.path.exists(dp), False)

    @raises(OSError)
    def test_cannot_delete_non_empty_dir(self):
        dp = os.path.join(self.tmp, 'path')
        with self.stor.open(os.path.join(dp, 'file.txt'), 'w') as fp:
            fp.write('stuff')
        self.stor.delete(dp)

    def test_delete_file(self):
        dp = os.path.join(self.tmp, 'path')
        fn = os.path.join(dp, 'file.txt')
        with self.stor.open(fn, 'w') as fp:
            fp.write('stuff')
        self.stor.delete(fn)
        eq_(os.path.exists(fn), False)
        eq_(os.path.exists(dp), True)


class TestCacheNamespaces(unittest.TestCase):

    def setUp(self):
        cache.clear()
        self.namespace = 'redis-is-dead'

    @mock.patch('amo.utils.epoch')
    def test_no_preexisting_key(self, epoch_mock):
        epoch_mock.return_value = 123456
        eq_(cache_ns_key(self.namespace), '123456:ns:%s' % self.namespace)

    @mock.patch('amo.utils.epoch')
    def test_no_preexisting_key_incr(self, epoch_mock):
        epoch_mock.return_value = 123456
        eq_(cache_ns_key(self.namespace, increment=True),
            '123456:ns:%s' % self.namespace)

    @mock.patch('amo.utils.epoch')
    def test_key_incr(self, epoch_mock):
        epoch_mock.return_value = 123456
        cache_ns_key(self.namespace)  # Sets ns to 123456
        ns_key = cache_ns_key(self.namespace, increment=True)
        expected = '123457:ns:%s' % self.namespace
        eq_(ns_key, expected)
        eq_(cache_ns_key(self.namespace), expected)


class TestEscapeAll(unittest.TestCase):

    def test_basics(self):
        x = '-'.join([u, u])
        y = ' - '.join([u, u])

        tests = [
            ('<script>alert("BALL SO HARD")</script>',
             '&lt;script&gt;alert("BALL SO HARD")&lt;/script&gt;'),
            (u'Bän...g (bang)', u'Bän...g (bang)'),
            (u, u),
            (x, x),
            (y, y),
            (u'x荿', u'x\u837f'),
            (u'ϧ΃蒬蓣', u'\u03e7\u0383\u84ac\u84e3'),
            (u'¿x', u'¿x'),
        ]

        for val, expected in tests:
            eq_(escape_all(val), expected)

    def test_nested(self):
        value = '<script>alert("BALL SO HARD")</script>'
        expected = '&lt;script&gt;alert("BALL SO HARD")&lt;/script&gt;'

        test = {
            'string': value,
            'dict': {'x': value},
            'list': [value],
            'bool': True,
        }
        res = escape_all(test)

        eq_(res['string'], expected)
        eq_(res['dict'], {'x': expected})
        eq_(res['list'], [expected])
        eq_(res['bool'], True)

    def test_without_linkify(self):
        value = '<button>http://firefox.com</button>'
        expected = '&lt;button&gt;http://firefox.com&lt;/button&gt;'

        test = {
            'string': value,
            'dict': {'x': value},
            'list': [value],
            'bool': True,
        }
        res = escape_all(test, linkify=False)

        eq_(res['string'], expected)
        eq_(res['dict'], {'x': expected})
        eq_(res['list'], [expected])
        eq_(res['bool'], True)


class TestAttachTransDict(amo.tests.TestCase):
    """
    Tests for attach_trans_dict. For convenience, we re-use Addon model instead
    of mocking one from scratch and we rely on internal Translation unicode
    implementation, because mocking django models and fields is just painful.
    """

    def test_basic(self):
        addon = amo.tests.addon_factory(
            name='Name', description='Description <script>alert(42)</script>!',
            homepage='http://home.pa.ge', privacy_policy='Policy',
            support_email='sup@example.com', support_url='http://su.pport.url')
        addon.save()

        # Quick sanity checks: is description properly escaped? The underlying
        # implementation should leave localized_string un-escaped but never use
        # it for __unicode__. We depend on this behaviour later in the test.
        ok_('<script>' in addon.description.localized_string)
        ok_(not '<script>' in addon.description.localized_string_clean)
        ok_(not '<script>' in unicode(addon.description))

        # Attach trans dict.
        attach_trans_dict(Addon, [addon])
        ok_(isinstance(addon.translations, collections.defaultdict))
        translations = dict(addon.translations)

        # addon.translations is a defaultdict.
        eq_(addon.translations['whatever'], [])

        # No-translated fields should be absent.
        ok_(None not in translations)

        # Build expected translations dict.
        expected_translations = {
            addon.privacy_policy_id: [
                ('en-us', unicode(addon.privacy_policy))],
            addon.description_id: [
                ('en-us', unicode(addon.description))],
            addon.homepage_id: [('en-us', unicode(addon.homepage))],
            addon.name_id: [('en-us', unicode(addon.name))],
            addon.support_email_id: [('en-us', unicode(addon.support_email))],
            addon.support_url_id: [('en-us', unicode(addon.support_url))]
        }
        eq_(translations, expected_translations)

    def test_multiple_objects_with_multiple_translations(self):
        addon = amo.tests.addon_factory()
        addon.description = {
            'fr': 'French Description',
            'en-us': 'English Description'
        }
        addon.save()
        addon2 = amo.tests.addon_factory(description='English 2 Description')
        addon2.name = {
            'fr': 'French 2 Name',
            'en-us': 'English 2 Name',
            'es': 'Spanish 2 Name'
        }
        addon2.save()
        attach_trans_dict(Addon, [addon, addon2])
        eq_(set(addon.translations[addon.description_id]),
            set([('en-us', 'English Description'),
                 ('fr', 'French Description')]))
        eq_(set(addon2.translations[addon2.name_id]),
            set([('en-us', 'English 2 Name'),
                 ('es', 'Spanish 2 Name'),
                 ('fr', 'French 2 Name')]))
