# ECOCOMMIT License Decision

Status: **OWNER DECISION REQUIRED — NO LICENSE SELECTED**

This note prepares the decision; it does not license the repository. Until the
owner adds a canonical license file, ordinary copyright restrictions remain and
Checkpoint E stays blocked. This is project planning, not legal advice.

## Options

| Option | Best fit | Main trade-off |
|---|---|---|
| **Apache License 2.0 — recommended** | Permissive public/enterprise adoption where an explicit contributor patent grant is valuable | More terms and notice discipline than MIT |
| **MIT** | The shortest, simplest permissive release | No similarly detailed express patent-license section |
| **GNU AGPL v3** | Requiring operators of modified network services to offer corresponding source to their users | Strong copyleft obligations can reduce proprietary adoption |
| **No license** | Keeping reuse rights reserved | Not an open-source release and remains an E blocker |

Primary references:

- Apache License 2.0 application guidance and canonical text:
  <https://www.apache.org/legal/apply-license> and
  <https://www.apache.org/licenses/LICENSE-2.0.html>
- OSI canonical MIT page: <https://opensource.org/license/mit>
- GNU license guidance describing the AGPL network-source condition:
  <https://www.gnu.org/licenses/>

## Recommended default

Choose **Apache-2.0** if ECOCOMMIT is intended for broad research, Buildathon,
and enterprise reuse. Its permissive model matches the public-repository goal,
while the express patent terms are useful for a protocol and safety architecture
that may attract organizational contributors.

## Owner checklist before selection

1. Confirm the owner has authority to license every original source and document.
2. Identify copied or generated assets that need separate attribution or terms.
3. Decide whether proprietary hosted derivatives are acceptable.
4. If choosing Apache-2.0, decide whether any attribution belongs in `NOTICE`.
5. Have counsel review the choice if the project will handle real payments or be
   commercialized.

## Mechanical follow-up after the owner decides

1. Add the unmodified canonical text as top-level `LICENSE`.
2. Add the matching SPDX identifier to project metadata.
3. Update README and Checkpoint E from `BLOCKED` only after validating the exact
   license contents, repository ownership, and any required notices.
4. Record the owner decision and date in the engineering log.
