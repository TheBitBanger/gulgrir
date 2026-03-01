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
    # path("filter/<int:pk>/", views.apply_saved_filter, name="apply_filter"),
    path("actions/", views.useritem_execute_action, name="useritem_actions"),
    path("actions/list/", views.list_actions, name="action_list"),
    path("actions/params/", views.action_params, name="action_params"),
]

tag_patterns = [
    path("", views.TagList.as_view(), name="tag_list"),
    path("add/", views.TagCreate.as_view(), name="tag_add"),
    path("quick-create/", views.TagQuickCreate.as_view(), name="tag_quick_create"),
]

queue_patterns = [
    path("", views.QueueList.as_view(), name="queue_manage"),
    path("add/", views.QueueCreate.as_view(), name="queue_add"),
    path("<int:pk>/edit/", views.QueueUpdate.as_view(), name="queue_edit"),
]

urlpatterns = [
    # queue views
    path("queues/", views.queue_list, name="queue_list"),
    path("queues/<int:pk>/", views.queue_detail, name="queue_detail"),
    path("no-queue/", views.no_queue, name="no_queue"),
    path("bulk-action/", views.bulk_history_action, name="bulk_action"),
    # crud section
    path("library/items/", include((item_patterns))),
    path("my/items/", include((useritem_patterns))),
    path("my/tags/", include((tag_patterns))),
    path("my/queues/", include((queue_patterns))),
    # preferences
    path("settings/preferences/", views.preference_view, name="preferences"),
]
