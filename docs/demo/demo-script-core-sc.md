# NEXUS Demo Script -- Core SC: Pre-Demo Instance Briefing
# Audience: ServiceNow Manager
# Duration: ~10-12 minutes of terminal time
# Author: Pierre Grothe
# Date: 2026-06-11

---

## Story

You are Taylor, a Core SC at ServiceNow.

You are 24 hours out from a product showcase with Luminar Group -- a
mid-market retailer evaluating ITSM + HR Service Delivery for 5,000 employees.
The afternoon before the demo, the customer's IT manager emails three questions:

  1. "Your demo instance -- is it running the exact plugin set a standard
     ITSM + HRSD deployment would include? We don't want to see features
     we can't license."

  2. "We noticed your demo has a Retail scope. We already use ServiceNow for
     basic IT Asset Management. Will there be plugin conflicts?"

  3. "Our integration team needs to know what tables ITSM workflows touch
     before we commit to a scoping call. Can you give us something concrete?"

Without NEXUS: three Slack threads, two colleagues on the phone, and a prayer
that someone remembers which instance is the clean ITSM demo vs the retail lab.

With NEXUS: 8 minutes, one terminal window, all three questions answered.

---

## Pre-flight (before recording)

  nexus reauth          # refresh tokens for alectri and retail
  nexus instance list   # confirm both instances show Connected

---

## Act 1 -- Know Your Environment (90 seconds)

Scene: Taylor opens a terminal. First instinct: establish what you are
working with.

  # What tier, what version, are enterprise servers up?
  nexus status

  [PAUSE] "This is my ground truth. PRO tier, two instances registered,
  no enterprise MCP dependencies needed for today's demo."

  # List all registered instances at a glance
  nexus instance list

  [PAUSE] "I have two: alectri -- my main ITSM demo -- and retail, which
  I configured for a different prospect last month. The question is which
  one to use today."

---

## Act 2 -- Pick the Right Instance (2 minutes)

Scene: The customer mentioned they already have IT Asset Management.
Taylor needs to know if the retail instance is too cluttered.

  # Compare plugin stacks between the two instances
  nexus plugins diff alectri retail

  [PAUSE] "Here is the exact delta. Retail has plugins that alectri does
  not -- and alectri has a cleaner ITSM + HRSD baseline. That answers the
  customer's first question: alectri is the right stage."

  # Set alectri as the active instance
  nexus instance use alectri

  # Full plugin inventory -- what is actually installed and active?
  nexus plugins list

  [PAUSE] "Every plugin, its version, its activation state. This is what
  the customer would get on a standard ITSM + HRSD deployment. No surprises,
  no hidden capabilities."

---

## Act 3 -- Answer the Hard Questions Live (3 minutes)

Scene: The customer asks about potential plugin conflicts with their
existing IT Asset Management setup.

  # Are there any EOL, CVE, or license advisories they should know about?
  nexus plugins advisories

  [PAUSE] "Proactive hygiene. If there is anything expired or at risk, I
  know about it before they do. Today the instance is clean."

  # Customer question: "We use com.snc.itam -- will that conflict?"
  nexus plugins explain com.snc.itam

  [PAUSE] "The AI reads the plugin metadata and reverse dependencies, then
  gives me a plain-language answer. I do not have to remember every plugin
  ID in the catalog -- I just ask."

  # Are there any orphaned plugins loaded on the demo that serve no purpose?
  nexus plugins orphans

  [PAUSE] "Orphans are plugins with no dependents and no scope-owned records.
  Dead weight. I remove these before every customer demo so the instance
  reflects a realistic, production-grade deployment."

  # Are there plugin updates available that I should apply before the demo?
  nexus plugins outdated

  [PAUSE] "Like brew outdated -- but for ServiceNow. If a plugin the customer
  will see is two versions behind, I patch it now, not after the call."

  # What plugins should I add to make this a best-practice ITSM + HRSD demo?
  nexus plugins recommend

  [PAUSE] "AI looks at what is installed and tells me what a complete ITSM
  + HRSD deployment for a mid-market retailer typically also includes. This
  is how I answer 'should we also license X?' on the spot instead of
  promising a follow-up."

---

## Act 4 -- Answer the Data Model Question (2 minutes)

Scene: The integration team needs to know exactly which tables the Document
Designer module uses -- they are building a custom integration and need the
field-level data model before the scoping call.

  # What schema products are available for reverse engineering?
  nexus schema products

  [PAUSE] "I have a community-maintained product catalog synced from our
  GitHub registry. Let me pull the Document Designer data model -- exact
  tables, field types, and cross-scope references."

  # Reverse-engineer Document Designer into a Mermaid ERD
  nexus schema erd doc-designer --profile alectri

  [PAUSE] "14 tables, 22 edges, cross-scope bridges -- all derived
  deterministically from sys_dictionary and sys_relationship on the live
  instance. The integration team sees exactly which tables and fields they
  are working with before the scoping call happens. No LLM involved."

  # Export as an SVG for the follow-up deck (default, no flag needed)
  nexus schema erd doc-designer --profile alectri -o docs/erd/doc-designer-demo.md

  [PAUSE] "SVG rendered by default alongside the Markdown. One command.
  Ready for a slide or the follow-up email."

---

## Act 5 -- Leave a Documented Baseline (1 minute)

Scene: Demo is done. Taylor wants a written record of what was running.

  # Export the plugin inventory to YAML for the follow-up document
  nexus plugins export --format yaml

  [PAUSE] "This YAML is my baseline. Next time this customer asks 'is your
  demo the same as last time?' I compare against this file in seconds."

  # What is the drift since the last recorded baseline?
  nexus plugins drift

  [PAUSE] "Zero drift. The instance is exactly as I left it after the last
  demo prep. That is the answer to 'can we trust the environment.'"

  # AI-generated action plan: what should we fix, upgrade, or add -- and in
  # what order?
  nexus plugins roadmap

  [PAUSE] "This is the leave-behind. NEXUS reads the advisories, the outdated
  list, and the recommend output, then drafts a prioritized remediation plan.
  I paste the relevant section into the follow-up email as 'Recommended Next
  Steps.' The customer gets a structured path forward, not a bullet list of
  plugin IDs."

---

## Closing Line (spoken, not typed)

"Ten minutes. Three questions answered, two instance environments compared,
one ERD and one AI roadmap in the follow-up email. That is what NEXUS is for."

---

## Commands Used (in order)

  nexus status
  nexus instance list
  nexus plugins diff alectri retail
  nexus instance use alectri
  nexus plugins list
  nexus plugins advisories
  nexus plugins explain com.snc.itam
  nexus plugins orphans
  nexus plugins outdated
  nexus plugins recommend
  nexus schema products
  nexus schema erd ham-itsm
  nexus schema erd ham-itsm --image svg
  nexus plugins export --format yaml
  nexus plugins drift
  nexus plugins roadmap

---

## Notes for Recording

- Use a terminal width of 120 cols: `asciinema rec -c "COLUMNS=120 nexus ..."` or set before recording.
- Pause 2-3 seconds after each command output before typing the next.
- The [PAUSE] markers above are narration cues, not typed.
- Token expiry: run `nexus reauth` before starting the recording session.
- If `plugins explain` requires an API call, budget ~5s latency; this is intentional -- show it thinking.
- `schema erd --image svg` requires Kroki to be running locally or NEXUS_KROKI_URL set.
