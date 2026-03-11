from django.conf import settings
from django.test.runner import DiscoverRunner


class ProjectDiscoverRunner(DiscoverRunner):
    def build_suite(self, test_labels=None, **kwargs):
        if not test_labels:
            test_labels = [str(settings.BASE_DIR)]
        self.top_level = str(settings.BASE_DIR)
        return super().build_suite(test_labels, **kwargs)
