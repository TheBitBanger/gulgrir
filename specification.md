A quiet, precise description—just the shape of the thing, without the machinery behind it.

---

# Functional Requirements Specification

## 1. Overview

The application is a **self-hostable web application** designed to help users track how their time is spent across different activities. Users can start and stop timers, manually add time entries, edit past records, and visualize how their time is distributed across activities and groups.

The system supports **multiple users**, with each user’s data isolated from others.

The application must be deployable through **Docker Compose** and accessible through a web browser.

---

# 2. Core Concepts

## 2.1 User

A user represents an individual account within the system.

Each user:

* Has their own activities, groups, timers, and statistics
* Does not share data with other users
* Authenticates locally within the application

Users configure:

* Timezone
* Notification preferences
* Webhook endpoints (optional)

---

# 3. Activities

Activities represent things a user spends time doing.

Examples:

* Writing
* Studying
* Programming
* Gaming
* Exercise

### Activity properties

An activity must support:

* Name
* Optional description
* Creation date
* Editable properties
* Ability to archive or disable

### Activity behavior

Users can:

* Create activities
* Edit activities
* Archive activities
* Delete activities

Archived activities remain visible in historical data but cannot be used to start new timers.

---

# 4. Timer Tracking

The system tracks time through timers associated with activities.

## 4.1 Single Active Timer

At any given moment:

* A user may have **only one active timer running**

Starting a new timer must:

* Automatically stop any currently running timer
* Start timing the selected activity

---

## 4.2 Timer Start

When a user starts a timer:

* A new time entry begins
* The start timestamp is recorded

---

## 4.3 Timer Stop

When a user stops the timer:

* The current time entry is closed
* The end timestamp is recorded

---

## 4.4 Timer Accuracy

The timer:

* Does not require second-level precision
* Minute-level accuracy is sufficient
* Minor discrepancies are acceptable

The interface may display time in minutes instead of seconds.

---

# 5. Manual Time Entry

Users must be able to add time manually.

Manual additions must support:

* Selecting an activity
* Adding a duration (+X minutes or hours)
* Optionally specifying the start time
* Editing after creation

Manual entries must integrate with statistics and reports exactly like timer-generated entries.

---

# 6. Editing Time Entries

Users can modify past entries.

Supported edits include:

* Changing activity
* Changing start time
* Changing end time
* Changing total duration
* Deleting entries

All changes must update aggregated statistics.

---

# 7. Time Data Model Behavior

Each recorded time segment must include:

* Activity
* Start timestamp
* End timestamp or duration
* Owner (user)

Entries represent intervals of time spent on an activity.

---

# 8. Grouping and Profiles

Activities can be organized for reporting purposes.

## 8.1 Group Profiles

A user can create multiple **group profiles**.

A profile represents a particular way of grouping activities.

Examples:

Profile A:

* Work
* Personal

Profile B:

* Project Alpha
* Project Beta
* Project Gamma

Profiles allow the same activities to be categorized differently depending on the user’s perspective.

---

## 8.2 Groups

Within each profile:

* Users create groups
* Activities can be assigned to groups

Groups exist only inside their profile.

---

## 8.3 Activity Assignments

An activity may appear in groups depending on the active profile.

Assignments affect:

* Statistics
* Visualizations

Assignments do not affect recorded time entries themselves.

---

# 9. Statistics and Visualization

The application must provide tools to analyze time usage.

## 9.1 Time Window Selection

Users must be able to view statistics for:

* Today
* This week
* This month
* Custom date ranges

---

## 9.2 Breakdown by Activity

Users can see:

* Total time spent per activity
* Comparisons between activities

---

## 9.3 Breakdown by Group

Users can view time aggregated by groups within a selected profile.

---

## 9.4 Additional Views

The system should support multiple visual representations such as:

* Charts
* Lists
* Summaries

The goal is to allow users to understand how their time was distributed during a given time window.

---

# 10. Notifications

The application supports reminders while a timer is running.

Users can configure:

* Notification interval (for example every X minutes)

Notifications occur while a timer is active.

Notification types:

* In-app notifications
* Webhook events

---

# 11. Webhooks

Users can configure webhook endpoints.

Webhook events must be triggered for relevant actions such as:

* Timer started
* Timer stopped
* Time entry created
* Time entry edited
* Time entry deleted

Webhook payloads must include sufficient information to identify:

* User
* Activity
* Time entry
* Event type
* Timestamp

The system must attempt delivery and retry if delivery fails.

---

# 12. API

The system must expose an API that allows external systems to:

* Retrieve activities
* Retrieve time entries
* Retrieve aggregated statistics
* Start or stop timers
* Create or modify entries

The API must respect user authentication and authorization.

---

# 13. Timezone Handling

The system must support a user-configurable timezone.

Rules:

* Timestamps are stored in a consistent canonical form
* Data is displayed relative to the user’s configured timezone
* Day-based statistics must respect the user’s timezone

---

# 14. Data Volume Expectations

The system should comfortably support:

* Approximately 10–100 time entries per day per user

---

# 15. Multi-User Behavior

The application must support multiple independent users.

Requirements:

* Users cannot access each other’s data
* Each user has separate activities, entries, and groups
* System behavior remains consistent regardless of number of users

---

# 16. Authentication

Authentication is handled locally within the application.

Requirements:

* Account creation
* Login
* Password management
* Session handling

External authentication providers are not required.

---

# 17. Data Export

Users must be able to export their data.

Exports must include:

* Activities
* Time entries
* Durations
* Timestamps

Supported formats may include structured formats such as CSV or JSON.

---

# 18. Web Application Requirements

The application must:

* Be accessible through a web browser
* Provide a responsive interface
* Allow the user to operate timers and manage data from the interface
* Display statistics and visualizations

---

# 19. Deployment Requirements

The application must be:

* Self-hostable
* Deployable through Docker Compose
* Runnable without requiring external cloud services

A standard deployment must include:

* The application service
* A database service
* Any required background processing services

The system must be able to start and operate using the provided compose configuration.

---

# 20. Data Integrity Expectations

The system must ensure:

* A user cannot have multiple active timers simultaneously
* Time entries are consistently recorded
* Edits correctly propagate to statistics
* Historical records remain accurate after modifications
