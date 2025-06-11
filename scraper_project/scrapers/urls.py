from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import test_connection, run_scraper_dash, run_dash_more_threads, run_management_command

router = DefaultRouter()

urlpatterns = [
    path('test-connection/', test_connection, name='test-connection'),
    path('run-scraper-dash/', run_scraper_dash, name='run-scraper-dash'),
    path('run-dash-more-threads/', run_dash_more_threads, name='run-dash-more-threads'),

    path('run-command/', run_management_command, name='run-management-command'),

]