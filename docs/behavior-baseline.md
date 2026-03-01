# Behavior Baseline (Django App)

Purpose: capture the current behavior as a feature inventory so we can align and validate during stabilization and migration.

Scope: existing Django app only (current behavior, not target rewrite).

Status legend:
- Implemented
- Buggy
- Not Implemented

Snapshot
- Date: TBD
- Version/Commit: TBD

## Media

| Feature | Status | Notes |
| --- | --- | --- |
| Global library items (title, media type) | Implemented | |

## Projects

| Feature | Status | Notes |
| --- | --- | --- |
| Projects as UserItems without Item link | Implemented | |

## User Items

| Feature | Status | Notes |
| --- | --- | --- |
| Create/edit/delete user items | Implemented | |
| Shelf state (Backlog/In Progress/Done) | Implemented | |
| Tier rating (S-F + unranked) | Implemented | |
| Filter bar (shelf/media/tags/projects/title) | Implemented | |
| Saved filters sidebar | Implemented | See "Saved Filters / Queues (Legacy)" note |
| Stack filters on top of SavedFilter | Buggy | |
| SavedFilter populates controls/URL | Buggy | |

## Lists

| Feature | Status | Notes |
| --- | --- | --- |
| User-defined lists | Not Implemented | |

## Ratings

| Feature | Status | Notes |
| --- | --- | --- |
| Tier rating system | Implemented | |
| Per-user custom rating system | Not Implemented | |

## Revisits

| Feature | Status | Notes |
| --- | --- | --- |
| Revisit history + last revisited date | Implemented | |
| Bulk mark revisited refreshes list | Buggy | |

## Reminders

| Feature | Status | Notes |
| --- | --- | --- |
| Revisit reminders | Not Implemented | |

## Random Picker

| Feature | Status | Notes |
| --- | --- | --- |
| Weighted random picker (age-weighted) | Implemented | |

## Providers

| Feature | Status | Notes |
| --- | --- | --- |
| Provider sync/import | Not Implemented | |

## Import/Export

| Feature | Status | Notes |
| --- | --- | --- |
| Export media + ratings | Not Implemented | |

## Time Tracking

| Feature | Status | Notes |
| --- | --- | --- |
| Timer subsystem | Not Implemented | |

## Authentication & Users

| Feature | Status | Notes |
| --- | --- | --- |
| Non-admin login page | Not Implemented | |

## Tags

| Feature | Status | Notes |
| --- | --- | --- |
| Per-user tags | Implemented | |
| Tag usage counts | Not Implemented | |
| Confirm delete when tags in use | Not Implemented | |
| Bulk tag edit | Not Implemented | |

## Preferences

| Feature | Status | Notes |
| --- | --- | --- |
| Date format + timezone preference | Implemented | |

## UI/UX

| Feature | Status | Notes |
| --- | --- | --- |
| Table inline "mark completed/revisited" controls | Not Implemented | TODO in useritem table |
| Light/Dark themes | Not Implemented | |

## Saved Filters / Queues (Legacy)

Note: queues are legacy and should be removed in favor of SavedFilters.

| Feature | Status | Notes |
| --- | --- | --- |
| Saved filters (per user) | Implemented | |
| Queues (saved filter DSL + ordering) | Implemented | Legacy |

## Maintenance / Tech Debt

| Feature | Status | Notes |
| --- | --- | --- |
| Remove apply_filter view (verify unused) | Not Implemented | |
| Remove commented code in build_useritem_queryset | Not Implemented | |
| Remove commented code in useritem_dashboard.html | Not Implemented | |
| Remove commented code in save_current_filter | Not Implemented | |
| Remove commented code in useritem_filter_bar.html | Not Implemented | |
| Remove useritem_saved_filters.html | Not Implemented | |
| Remove commented code from urls.py | Not Implemented | |
| Remove htmx:afterSettle block in base.html | Not Implemented | |
| Remove queue objects (models/views/templates) | Not Implemented | |
| Continue moving code from views -> services | Not Implemented | |
| Clean SavedFilters UI | Not Implemented | |
| Align admin env vars with createsuperuser_if_none | Implemented | |

## Operations / Backups

| Feature | Status | Notes |
| --- | --- | --- |
| Improve backup/restore workflow (shorter commands, helper image or app command, env-driven paths, POSTGRES_DB var, rotation/retention) | Not Implemented | |
