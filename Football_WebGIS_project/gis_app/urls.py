# gis_app/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.map_view, name='map_page'),
    path('identify/', views.identify_feature, name='identify-feature'),
    path('search/', views.search, name='search'),
    path('statistics/', views.get_state_statistics, name='state-statistics'),
    path('statistics/all/', views.all_states_statistics, name='all-states-statistics'),
    path('stadiums/create/', views.create_stadium, name='create-stadium'),
    path('stadiums/update/<int:objectid>/', views.update_stadium, name='update_stadium'),

    path('nearest/', views.nearest_stadium, name='nearest_stadium'),
]

