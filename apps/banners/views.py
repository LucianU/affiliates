import json
import logging
import socket

from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache

from funfactory.urlresolvers import reverse

from badges.views import dashboard
from banners import tasks
from banners.forms import BannerForm
from banners.models import Banner, BannerImage, BannerInstance
from shared.decorators import login_required
from shared.utils import redirect


CACHE_LINK_INSTANCE = 'banner_link_instance_%s_%s'
log = logging.getLogger('a.banners')


@login_required
def customize(request, banner_pk=None):
    banner = get_object_or_404(Banner, pk=banner_pk)

    # Create a new banner
    form = BannerForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        image = form.cleaned_data['image']
        instance, created = BannerInstance.objects.get_or_create(
            badge=banner, user=request.user, image=image)
        return redirect('my_badges', anchor='banner_%s' % instance.pk)

    back_href = reverse('badges.new.step2',
                        kwargs={'subcategory_pk': banner.subcategory.pk})
    banner_images = BannerImage.objects.customize_values(banner=banner)

    return dashboard(request, 'banners/customize.html',
                     {'back_href': back_href,
                      'banner': banner,
                      'banner_images': json.dumps(banner_images),
                      'form': form,
                      'subcategory': banner.subcategory})


@never_cache
def link(request, banner_instance_id):
    """Handle banner link."""
    try:
        instance = (BannerInstance.objects.select_related('badge')
                    .get(pk=banner_instance_id))
    except BannerInstance.DoesNotExist:
        return HttpResponseRedirect(settings.DEFAULT_AFFILIATE_LINK)

    try:
        tasks.add_click.delay(banner_instance_id)
    except socket.timeout:
        log.warning('Timeout connecting to celery for banner click.')

    return HttpResponseRedirect(instance.badge.href)


@never_cache
def old_link(request, user_id, banner_id, banner_img_id):
    """Legacy handler for old banner links."""
    try:
        banner = Banner.objects.get(pk=banner_id)
    except Banner.DoesNotExist:
        return HttpResponseRedirect(settings.DEFAULT_AFFILIATE_LINK)

    try:
        tasks.old_add_click.delay(user_id, banner_id, banner_img_id)
    except socket.timeout:
        log.warning('Timeout connecting to celery for banner click.')

    return HttpResponseRedirect(banner.href)
