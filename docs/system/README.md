# System

What gulgrir must do, why, and how it is built. Cross-cutting documents live here; each
domain folder holds its own.

- [requirements.md](requirements.md) — purpose, audience, cross-cutting needs, and what is out of scope
- [design.md](design.md) — how the system meets its cross-cutting requirements, such as running beside Django, and how that is verified
- [decisions/](decisions/README.md) — numbered decision records

| Domain                                | Provides                                                       |
| ------------------------------------- | -------------------------------------------------------------- |
| [accounts](accounts/)                 | users, isolation, administration                               |
| [library](library/)                   | tracked items, personal data, tags, filters, collections      |
| [metadata](metadata/)                 | matching items to real works and keeping catalog data current |
| [configuration](configuration/)       | settings, their start-up report, and what stops start-up       |
| [import](import/)                     | bringing in lists from other services and files               |
| [lifecycle](lifecycle/)               | stages from wishlist to done, and completion history          |
| [selection](selection/)               | suggesting the next item from a set                            |
| [notifications](notifications/)       | new-release alerts and revisit reminders                       |
| [time-tracking](time-tracking/)       | time records, groups, goals, and time metrics                  |
| [recommendations](recommendations/)   | suggesting new things to add                                   |
