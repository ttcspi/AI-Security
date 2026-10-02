# AI-Security lab — spin up the target servers.
# Targets are auto-discovered from targets/*/server.py, so adding a target needs no edits here.
#
#   make up                 start every target
#   make down               stop every target
#   make restart            stop then start every target
#   make ps                 status of every target
#   make up-<name>          start one      (e.g. make up-chungus-hr)
#   make down-<name>        stop one
#   make logs-<name>        follow one target's log
#
# Attacks live in attackers/attacker-agent (`./attack ...`); this Makefile only runs the targets.
SHELL := /bin/bash
PY ?= python3
CTL := scripts/targetctl.sh
TARGETS := $(patsubst targets/%/server.py,%,$(wildcard targets/*/server.py))

.PHONY: help up down restart ps $(addprefix up-,$(TARGETS)) $(addprefix down-,$(TARGETS)) $(addprefix logs-,$(TARGETS))

help:
	@echo "AI-Security lab — target servers (discovered: $(TARGETS))"
	@echo "  make up            start every target"
	@echo "  make down          stop every target"
	@echo "  make restart       stop then start every target"
	@echo "  make ps            status of every target"
	@echo "  make up-<name>     start one   (e.g. make up-chungus-hr)"
	@echo "  make down-<name>   stop one"
	@echo "  make logs-<name>   follow one target's log"

up: $(addprefix up-,$(TARGETS))
down: $(addprefix down-,$(TARGETS))
restart: down up

ps:
	@echo "  target status:"
	@for t in $(TARGETS); do $(CTL) status $$t; done

$(foreach t,$(TARGETS),$(eval up-$(t): ; @$(CTL) start $(t)))
$(foreach t,$(TARGETS),$(eval down-$(t): ; @$(CTL) stop $(t)))
$(foreach t,$(TARGETS),$(eval logs-$(t): ; @$(CTL) logs $(t)))
