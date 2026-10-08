# System requirements

Gulgrir keeps every backlog in one place: books, films, shows, games, music, anime, manga,
light novels and personal projects. It helps the user rotate through them, so binging one
thing doesn't bury everything else.

## Who it is for

The primary user is the author: someone with a large backlog spread over many services and
notepads, who also works on side projects. They tend to get absorbed in one thing and forget
the rest, and they want time spread evenly across areas, for example about as much on books as
on films, and on work projects as on leisure. No existing tool does all of this.

The product is packaged for others like them: self-hosting hobbyists with basic hosting
skills, who value privacy.

## Cross-cutting requirements

| ID    | Need                                                                                                                                  | Why                                                                         |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| SYS-1 | A user needs every consumption list and project in one place instead of spread over many sites.                                       | So nothing in the backlog is forgotten and no lists need juggling.          |
| SYS-2 | The same lists need to serve personal projects and hobbies, not only media.                                                           | So work and play rotate by the same rules.                                  |
| SYS-3 | A user's data needs to stay on hardware they control and never be sold, profiled, or used for ads.                                    | Privacy is why they self-host.                                              |
| SYS-4 | Someone with basic self-hosting skills needs to install, upgrade, and run the system without expert help.                             | That is the audience.                                                       |
| SYS-5 | The system needs to run on a Linux host, Debian first. Other platforms are a bonus.                                                   | That is what the audience runs.                                             |
| SYS-6 | One instance needs to serve up to about 100 accounts.                                                                                 | It is a hobbyist product, not a service.                                    |
| SYS-7 | A user needs to use the product from both desktop and phone.                                                                          | Timers, quick look-ups ("have I seen this?") and recommendations happen away from a desk. |
| SYS-8 | A user needs numbers and charts about their library and their time.                                                                   | So they can see their patterns and adjust how they work.                    |
| SYS-9 | An administrator needs instance backups that can be restored.                                                                         | Losing a library curated over years is the worst failure.                   |
| SYS-10 | Data already in the running instance (items, history, tags, filters, time entries) needs to survive any change of technology.        | The system is in daily use.                                                 |

## Out of scope

| Not doing                                       | Why                                                        |
| ----------------------------------------------- | ---------------------------------------------------------- |
| Acquiring or downloading media                  | Other tools, like the \*arr stack, do this well.           |
| Managing media files                            | Same.                                                      |
| Working offline                                 | Too much effort for the value; revisit if it becomes important. |
| Sharing lists or boards between users           | Nobody needs it yet.                                       |
| Writing back to external services               | Gulgrir is authoritative; data only flows in.              |
| User-defined lifecycle stages                   | Standard stages plus tags cover real workflows.            |
