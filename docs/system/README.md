# System

What gulgrir must do and why. Cross-cutting requirements live here; each domain folder holds
its own.

- [requirements.md](requirements.md) — purpose, audience, cross-cutting needs, and what is out of scope
- [decisions/](decisions/README.md) — numbered decision records

| Domain                                | Provides                                                       |
| ------------------------------------- | -------------------------------------------------------------- |
| [accounts](accounts/)                 | users, isolation, administration                               |
| [library](library/)                   | tracked items, personal data, tags, filters, collections      |
| [metadata](metadata/)                 | matching items to real works and keeping catalog data current |
| [import](import/)                     | bringing in lists from other services and files               |
| [lifecycle](lifecycle/)               | stages from wishlist to done, and completion history          |
| [selection](selection/)               | suggesting the next item from a set                            |
| [notifications](notifications/)       | new-release alerts and revisit reminders                       |
| [time-tracking](time-tracking/)       | time records, groups, goals, and time metrics                  |
| [recommendations](recommendations/)   | suggesting new things to add                                   |
