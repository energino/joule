#!/usr/bin/env python

import sys
from distutils.core import setup

if sys.version < '2.7':
	raise ValueError("Sorry Python versions older than 2.7 are not supported")

setup(name="joule",
	version="0.1",
	description="Joule",
	author="Roberto Riggio",
	author_email="roberto.riggio@create-net.org",
	url="https://github.com/rriggio/joule",
	long_description="Joule is an energy consumption profiler for WLANs",
	data_files = [('etc/', ['xively.conf'])],
	entry_points={"console_scripts": ["joule-daemon=joule.daemon:main", "joule-profiler=joule.profiler:main", "joule-modeller=joule.modeller:main", "joule-dumpcsv=joule.dumpcsv:main", "joule-template=joule.template:main"]},
	packages=['joule'],
	license = "Python",
	platforms="any"
)

