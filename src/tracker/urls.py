from django.urls import path, include

from . import views

item_patterns = [
    path("", views.ItemList.as_view(), name="item_list"),
    path("add/", views.ItemCreate.as_view(), name="item_add"),
]

useritem_patterns = [
    path("", views.useritem_dashboard, name="useritem_dashboard"),
    path("add/", views.UserItemCreate.as_view(), name="useritem_add"),
    path("<int:pk>/edit/", views.UserItemUpdate.as_view(), name="useritem_edit"),
    path("<int:pk>/delete/", views.UserItemDelete.as_view(), name="useritem_delete"),
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
    path("bulk-action/", views.bulk_history_action, name="bulk_action"),
    # crud section
    path("library/items/", include((item_patterns))),
    path("my/items/", include((useritem_patterns))),
    path("my/tags/", include((tag_patterns))),
    path("my/filters/", include((saved_filter_patterns))),
    # preferences
    path("settings/preferences/", views.preference_view, name="preferences"),
]
