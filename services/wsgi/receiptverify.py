import os
import site

os.environ['DJANGO_SETTINGS_MODULE'] = 'settings_local_mkt'

wsgidir = os.path.dirname(__file__)
for path in ['../',
             '../..',
             '../../..',
             '../../vendor/lib/python']:
    site.addsitedir(os.path.abspath(os.path.join(wsgidir, path)))

from verify import application
