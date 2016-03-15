# -*- coding: utf8 -*-

import json

import requests
from django.conf import settings
from django.contrib.gis.geos import Point
from django.utils.translation import ugettext as _

from geotrek.common.parsers import (AttachmentParserMixin, Parser,
                                    GlobalImportError)
from geotrek.tourism.models import TouristicContent


class TouristicContentSitraParser(AttachmentParserMixin, Parser):
    """Parser to import touristic contents from SITRA"""
    api_key = None
    project_id = None
    selection_id = None
    category = None
    type1 = None
    type2 = None
    url = 'http://api.sitra-tourisme.com/api/v002/recherche/list-objets-touristiques/'
    model = TouristicContent
    eid = 'eid'
    fields = {
        'eid': 'id',
        'name': 'nom.libelleFr',
        'description': 'presentation.descriptifCourt.libelleFr',
        'contact': (
            'localisation.adresse.adresse1',
            'localisation.adresse.adresse2',
            'localisation.adresse.codePostal',
            'localisation.adresse.commune.nom',
            'informations.moyensCommunication',
        ),
        'email': 'informations.moyensCommunication',
        'website': 'informations.moyensCommunication',
        'geom': 'localisation.geolocalisation.geoJson.coordinates',
    }
    constant_fields = {
        'published': True,
    }
    m2m_constant_fields = {
    }
    non_fields = {
        'attachments': 'illustrations',
    }
    natural_keys = {
        'category': 'label',
        'type1': 'label',
    }
    field_options = {
        'name': {'required': True},
        'geom': {'required': True},
    }

    def __init__(self, *args, **kwargs):
        super(TouristicContentSitraParser, self).__init__(*args, **kwargs)
        if self.category:
            self.constant_fields['category'] = self.category
        if self.type1:
            self.m2m_constant_fields['type1'] = self.type1
        if self.type2:
            self.m2m_constant_fields['type2'] = self.type2

    @property
    def items(self):
        return self.root['objetsTouristiques']

    def next_row(self):
        size = 100
        skip = 0
        while True:
            params = {
                'apiKey': self.api_key,
                'projetId': self.project_id,
                'selectionIds': [self.selection_id],
                'count': size,
                'first': skip,
            }
            response = requests.get(self.url, params={'query': json.dumps(params)})
            if response.status_code != 200:
                msg = _(u"Failed to download {url}. HTTP status code {status_code}")
                raise GlobalImportError(msg.format(url=response.url, status_code=response.status_code))
            self.root = response.json()
            self.nb = int(self.root['numFound'])
            for row in self.items:
                yield row
            skip += size
            if skip >= self.nb:
                return

    def filter_attachments(self, src, val):
        result = []
        for subval in val or []:
            if 'nom' in subval:
                name = subval['nom'].get('libelleFr')
            else:
                name = None
            result.append((subval['traductionFichiers'][0]['url'], name, None))
        return result

    def normalize_field_name(self, name):
        return name

    def filter_eid(self, src, val):
        return unicode(val)

    def filter_comm(self, val, code):
        if not val:
            return None
        for subval in val:
            if subval['type']['id'] == code:
                return subval['coordonnees']['fr']

    def filter_email(self, src, val):
        return self.filter_comm(val, 204)

    def filter_website(self, src, val):
        return self.filter_comm(val, 205)

    def filter_contact(self, src, val):
        (address1, address2, zipCode, commune, comm) = val
        tel = self.filter_comm(comm, 201)
        if tel:
            tel = u"Tél. " + tel
        lines = [line for line in [
            address1,
            address2,
            ' '.join([part for part in [zipCode, commune] if part]),
            tel,
        ] if line]
        return '<br>'.join(lines)

    def filter_geom(self, src, val):
        lng, lat = val
        geom = Point(float(lng), float(lat), srid=4326)  # WGS84
        geom.transform(settings.SRID)
        return geom


class EspritParcParser(AttachmentParserMixin, Parser):
    model = TouristicContent
    eid = 'eid'
    separator = None
    delete = True
    fields = {
        'eid': 'eid',
        'name': 'nomCommercial',
        'description': 'descriptionDetaillee',
        'practical_info': 'informationsPratiques',
        'category': 'type.0.label',
        'contact': (
            'contact.adresse',
            'contact.codePostal',
            'contact.commune',
            'contact.telephone',
            'contact.gsm',
            'contact.fax',
            'contact.facebook',
            'contact.twitter'
        ),
        'email': 'contact.courriel',
        'website': 'contact.siteWeb',
        'geom': 'geo',
    }

    constant_fields = {
        'published': True,
        'approved': True
    }

    field_options = {
        'name': {'required': True, },
        'geom': {'required': True, },
        'category': {'create': True},
        'type1': {'create': True},
        'type2': {'create': True},
    }

    natural_keys = {
        'category': 'label',
        'type1': 'label',
        'type2': 'label'
    }

    m2m_fields = {
        'type1': 'sousType.*.label',
        'type2': 'classement.*.labelType',
    }

    non_fields = {
        'attachments': 'photo',
    }

    def filter_attachments(self, src, val):
        result = []
        for subval in val or []:
            if 'url' in subval:
                result.append((subval['url'],
                               subval.get('legend', None),
                               subval.get('credits', None)))
        return result

    @property
    def items(self):
        return self.root['responseData']

    def next_row(self):
        response = requests.get(self.url)
        if response.status_code != 200:
            msg = _(u"Failed to download {url}. HTTP status code {status_code}")
            raise GlobalImportError(msg.format(url=response.url,
                                               status_code=response.status_code))

        self.root = response.json()
        self.nb = int(self.root['numFound'])

        for row in self.items:
            yield row

    def normalize_field_name(self, name):
        return name

    def filter_eid(self, src, val):
        return u"{}".format(val)

    def filter_contact(self, src, val):
        (address, zipCode, commune, telephone, gsm, fax, facebook, twitter) = val
        cp_com = u' '.join([part for part in (zipCode, commune) if part])
        return u'<br>'.join([part for part in (address, cp_com, telephone, gsm, fax, facebook, twitter) if part])

    def filter_geom(self, src, val):
        lng = val['lon']
        lat = val['lat']
        geom = Point(float(lng), float(lat), srid=4326)  # WGS84
        geom.transform(settings.SRID)
        return geom

    def filter_name(self, src, val):
        return val[:128]

    def filter_category(self, src, val):
        if not val:
            return None

        return self.apply_filter('category', src, val)
