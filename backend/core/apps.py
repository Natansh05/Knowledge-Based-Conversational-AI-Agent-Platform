from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'
    def ready(self):
        import nltk
        nltk.download('stopwords')
        nltk.download('punkt_tab')