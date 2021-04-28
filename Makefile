# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

NAME := cloudblue-connector
DESTDIR ?= /
SYSCONFDIR ?= /etc
UNITDIR ?= /usr/lib/systemd/system
BINDIR ?= /usr/bin
PYTHON ?= /usr/bin/python2
INSTALL ?= /usr/bin/install
SERVICE_UNITS = cloudblue-fulfillments.service cloudblue-usage.service cloudblue-usage-files.service
CONFIGS = config.json.example config-logging.json.example
LOGDIR ?= /var/log/cloudblue-connector

all:
	$(PYTHON) setup.py build

install:
	$(PYTHON) setup.py install --skip-build --root $(DESTDIR) --install-scripts $(BINDIR)
	mkdir -p -m 0755 $(DESTDIR)/$(UNITDIR)
	for f in $(SERVICE_UNITS); do \
		 $(INSTALL) -m 0644 $$f $(DESTDIR)/$(UNITDIR); \
	done
	mkdir -p -m 0755 $(DESTDIR)/$(SYSCONFDIR)/$(NAME)
	for f in $(CONFIGS); do \
		$(INSTALL) -m 0644 $$f $(DESTDIR)/$(SYSCONFDIR)/$(NAME); \
	done
	mkdir -p -m 0700 $(DESTDIR)/$(LOGDIR)

rpm:
	mkdir -p ./build/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}; \
	export VERSION=$$(sed -n -e  's/%define current_version //p' cloudblue-connector.spec | sed -e 's/^[[:space:]]*//'); \
	rsync --exclude=build --exclude=dist -av `pwd`/ ./build/SOURCES/cloudblue-connector-$$VERSION; \
	cd ./build/SOURCES && tar -cvjSf cloudblue-connector-$$VERSION.tar.bz2 cloudblue-connector-$$VERSION; cd -; \
	rpmbuild -ba --define "_topdir `pwd`/build" cloudblue-connector.spec

.PHONY: all clean install test rpm
