web: python scraper_project/manage.py collectstatic --noinput && gunicorn scraper_project.scraper_project.wsgi:application --bind 0.0.0.0:$PORT
