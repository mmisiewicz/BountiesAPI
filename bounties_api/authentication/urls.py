from django.conf.urls import url
from authentication import views
from django.conf.urls import url, include
from rest_framework.routers import DefaultRouter


router = DefaultRouter()
router.register(r'user', views.UserAddressView)

urlpatterns = [
    url(r'^', include(router.urls)),
    url(r'^login/$', views.Login.as_view()),
    url(r'^logout/$', views.Logout.as_view()),
    url(r'^user/$', views.UserView.as_view()),
    url(r'^user/(?P<address>\w+)/nonce/$', views.Nonce.as_view()),
]