> Sent 2026-06-30, pre-v2 coverage -- current scope is broader; see verification-summary.md (v2 section).

Subject: Re: Comparing existing vs. new instance -- replatform checklists

Hi,

Yes -- that is squarely what the assess part of the tool does. There are two
commands:

- `nexus assess inventory <instance>` -- builds a use-case inventory of one
  instance's custom configuration.
- `nexus assess migration --from <old> --to <new>` -- compares the two
  instances and produces a checklist of the use cases and workflows the new,
  clean instance still needs.

The checklist is markdown with task-list checkboxes that tick themselves as you
build things out on the new instance (just re-run it to refresh). Every item is
statused:

- DONE    -- already exists on the new instance
- TODO    -- on the old instance, not yet on the new one (your build list)
- PARTIAL -- a use case partly migrated, with a built/total fraction
- EXTRA   -- on the new instance but not the old (so you can catch scope creep)

It matches artifacts by normalized name rather than internal IDs (so a rebuilt
workflow still matches its original), and there is a `--scope-alias OLD=NEW`
option for apps whose scope gets renamed on the new instance. It is strictly
read-only -- it never touches either instance.

To make this concrete rather than a claim, I ran it live against two real
ServiceNow instances and attached the output:

- The OLD instance had 558 custom AI/automation workflows; the NEW one had 553.
- The tool produced a checklist marking 553 DONE and 5 TODO (the exact 5
  workflows the new instance still needs), with the use case rolling up to
  PARTIAL 553/558 -- and the whole comparison ran in about 10 seconds.
- I spot-checked two items against the raw data: a workflow it flagged TODO is
  genuinely missing from the new instance, and one it flagged DONE is genuinely
  on both. (Details in the verification summary.)

One honest scoping note so I am not overselling it: today the inventory covers
your custom AI & Automation artifacts -- Flows and subflows, IntegrationHub
actions, Virtual Agent topics, NowAssist skills, and AI Agents. Broader
configuration coverage (business rules, UI policies, ACLs, catalog items, and
so on) and grouping custom apps into named product domains are the next
milestone. If CIBC's replatform is largely flow/automation-driven, it is a
direct fit today; if it spans every customization type, I would set expectations
that the current release covers that AI & Automation surface.

Attached:
- replatform-checklist.md  -- the actual generated checklist (sample run)
- capability-sheet.md      -- one page on what it does and what it covers
- verification-summary.md  -- the numbers above and how they were checked
- run-transcript.txt       -- the terminal transcript of the run

Happy to run it against a CIBC sandbox pair and walk you through a real
checklist whenever it is useful.

Best,
Pierre
