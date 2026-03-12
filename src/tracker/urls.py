from django.contrib.auth import views as auth_views
from django.urls import path, include

from .views import actions, items, preferences, saved_filters, tags, time_tracking, useritems

item_patterns = [
    path("", items.ItemList.as_view(), name="item_list"),
    path("add/", items.ItemCreate.as_view(), name="item_add"),
]

useritem_patterns = [
    path("", useritems.useritem_dashboard, name="useritem_dashboard"),
    path("add/", useritems.UserItemCreate.as_view(), name="useritem_add"),
    path("<int:pk>/", useritems.UserItemDetail.as_view(), name="useritem_detail"),
    path("<int:pk>/edit/", useritems.UserItemUpdate.as_view(), name="useritem_edit"),
    path("<int:pk>/delete/", useritems.UserItemDelete.as_view(), name="useritem_delete"),
    path("<int:pk>/complete/", useritems.useritem_complete, name="useritem_complete"),
    path("<int:pk>/restart/", useritems.useritem_restart, name="useritem_restart"),
    path(
        "<int:pk>/timer/start/",
        useritems.useritem_timer_start,
        name="useritem_timer_start",
    ),
    path(
        "<int:pk>/timer/stop/",
        useritems.useritem_timer_stop,
        name="useritem_timer_stop",
    ),
    path("<int:pk>/pin/", useritems.useritem_pin, name="useritem_pin"),
    path("<int:pk>/unpin/", useritems.useritem_unpin, name="useritem_unpin"),
    path(
        "<int:pk>/timer/add/",
        useritems.useritem_timer_add_retro,
        name="useritem_timer_add",
    ),
    path("save-filter/", saved_filters.save_current_filter, name="save_filter"),
    path("actions/", actions.useritem_execute_action, name="useritem_actions"),
    path("actions/list/", actions.list_actions, name="action_list"),
    path("actions/params/", actions.action_params, name="action_params"),
]

tag_patterns = [
    path("", tags.TagList.as_view(), name="tag_list"),
    path("add/", tags.TagCreate.as_view(), name="tag_add"),
    path("<int:pk>/edit/", tags.TagUpdate.as_view(), name="tag_edit"),
    path("<int:pk>/delete/", tags.TagDelete.as_view(), name="tag_delete"),
    path("quick-create/", tags.TagQuickCreate.as_view(), name="tag_quick_create"),
]

saved_filter_patterns = [
    path("", saved_filters.SavedFilterList.as_view(), name="saved_filter_list"),
    path(
        "<int:pk>/edit/",
        saved_filters.SavedFilterUpdate.as_view(),
        name="saved_filter_edit",
    ),
    path(
        "<int:pk>/delete/",
        saved_filters.SavedFilterDelete.as_view(),
        name="saved_filter_delete",
    ),
]

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("bulk-action/", actions.bulk_history_action, name="bulk_action"),
    # crud section
    path("library/items/", include((item_patterns))),
    path("my/items/", include((useritem_patterns))),
    path("my/tags/", include((tag_patterns))),
    path("my/filters/", include((saved_filter_patterns))),
    path("my/time/", time_tracking.time_dashboard, name="time_dashboard"),
    path("my/time/settings/", time_tracking.time_settings, name="time_settings"),
    path(
        "my/time/layouts/add/",
        time_tracking.time_layout_create,
        name="time_layout_add",
    ),
    path(
        "my/time/layouts/update/",
        time_tracking.time_layout_update,
        name="time_layout_update",
    ),
    path(
        "my/time/layouts/delete/",
        time_tracking.time_layout_delete,
        name="time_layout_delete",
    ),
    path(
        "my/time/buckets/add/",
        time_tracking.time_bucket_create,
        name="time_bucket_add",
    ),
    path(
        "my/time/buckets/update/",
        time_tracking.time_bucket_update,
        name="time_bucket_update",
    ),
    path(
        "my/time/buckets/delete/",
        time_tracking.time_bucket_delete,
        name="time_bucket_delete",
    ),
    path(
        "my/time/assign/",
        time_tracking.time_assignment_update,
        name="time_assignment_update",
    ),
    path(
        "my/time/select/",
        time_tracking.time_level_select,
        name="time_level_select",
    ),
    # preferences
    path("settings/preferences/", preferences.preference_view, name="preferences"),
]
