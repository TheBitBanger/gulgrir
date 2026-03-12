from django.contrib.auth import views as auth_views
from django.urls import path, include

from . import views

item_patterns = [
    path("", views.ItemList.as_view(), name="item_list"),
    path("add/", views.ItemCreate.as_view(), name="item_add"),
]

useritem_patterns = [
    path("", views.useritem_dashboard, name="useritem_dashboard"),
    path("add/", views.UserItemCreate.as_view(), name="useritem_add"),
    path("<int:pk>/", views.UserItemDetail.as_view(), name="useritem_detail"),
    path("<int:pk>/edit/", views.UserItemUpdate.as_view(), name="useritem_edit"),
    path("<int:pk>/delete/", views.UserItemDelete.as_view(), name="useritem_delete"),
    path("<int:pk>/complete/", views.useritem_complete, name="useritem_complete"),
    path("<int:pk>/restart/", views.useritem_restart, name="useritem_restart"),
    path(
        "<int:pk>/timer/start/",
        views.useritem_timer_start,
        name="useritem_timer_start",
    ),
    path("<int:pk>/timer/stop/", views.useritem_timer_stop, name="useritem_timer_stop"),
    path("<int:pk>/pin/", views.useritem_pin, name="useritem_pin"),
    path("<int:pk>/unpin/", views.useritem_unpin, name="useritem_unpin"),
    path("<int:pk>/timer/add/", views.useritem_timer_add_retro, name="useritem_timer_add"),
    path("save-filter/", views.save_current_filter, name="save_filter"),
    path("actions/", views.useritem_execute_action, name="useritem_actions"),
    path("actions/list/", views.list_actions, name="action_list"),
    path("actions/params/", views.action_params, name="action_params"),
]

tag_patterns = [
    path("", views.TagList.as_view(), name="tag_list"),
    path("add/", views.TagCreate.as_view(), name="tag_add"),
    path("<int:pk>/edit/", views.TagUpdate.as_view(), name="tag_edit"),
    path("<int:pk>/delete/", views.TagDelete.as_view(), name="tag_delete"),
    path("quick-create/", views.TagQuickCreate.as_view(), name="tag_quick_create"),
]

saved_filter_patterns = [
    path("", views.SavedFilterList.as_view(), name="saved_filter_list"),
    path("<int:pk>/edit/", views.SavedFilterUpdate.as_view(), name="saved_filter_edit"),
    path(
        "<int:pk>/delete/",
        views.SavedFilterDelete.as_view(),
        name="saved_filter_delete",
    ),
]

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("bulk-action/", views.bulk_history_action, name="bulk_action"),
    # crud section
    path("library/items/", include((item_patterns))),
    path("my/items/", include((useritem_patterns))),
    path("my/tags/", include((tag_patterns))),
    path("my/filters/", include((saved_filter_patterns))),
    path("my/time/", views.time_dashboard, name="time_dashboard"),
    path("my/time/settings/", views.time_settings, name="time_settings"),
    path("my/time/layouts/add/", views.time_layout_create, name="time_layout_add"),
    path(
        "my/time/layouts/update/",
        views.time_layout_update,
        name="time_layout_update",
    ),
    path(
        "my/time/layouts/delete/",
        views.time_layout_delete,
        name="time_layout_delete",
    ),
    path("my/time/buckets/add/", views.time_bucket_create, name="time_bucket_add"),
    path(
        "my/time/buckets/update/",
        views.time_bucket_update,
        name="time_bucket_update",
    ),
    path(
        "my/time/buckets/delete/",
        views.time_bucket_delete,
        name="time_bucket_delete",
    ),
    path("my/time/assign/", views.time_assignment_update, name="time_assignment_update"),
    path("my/time/select/", views.time_level_select, name="time_level_select"),
    # preferences
    path("settings/preferences/", views.preference_view, name="preferences"),
]
