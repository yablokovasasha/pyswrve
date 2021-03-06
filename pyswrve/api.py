# -*- coding: utf-8 -*-

import requests, re, sys, os.path
from datetime import date, timedelta

if sys.version_info[0] < 3:  # Python 2
    from ConfigParser import SafeConfigParser
else:  # Python 3
    from configparser import SafeConfigParser

class SwrveSession(object):

    # Default swrve's KPI factors
    kpi_factors = ['dau', 'mau', 'dau_mau', 'new_users', 'dpu', 'conversion',
                   'dollar_revenue', 'currency_spent', 'currency_spent_dau',
                   'currency_purchased', 'currency_purchased_dau',
                   'currency_given', 'items_purchased', 'items_purchased_dau',
                   'session_count', 'avg_session_length', 'arpu_daily',
                   'arppu_daily', 'arpu_monthly', 'arppu_monthly',
                   'avg_playtime', 'day30_retention']

    # Factors which are need tax calculation
    kpi_taxable = ('dollar_revenue', 'arpu_daily', 'arppu_daily',
                   'arpu_monthly', 'arppu_monthly')

    for i in (1, 3, 7):
        kpi_factors.append('day%s_reengagement' % i)
        kpi_factors.append('day%s_retention' % i)

    kpi_factors = tuple(kpi_factors)  # convert list to tuple

    # INI config file parser
    __prs = SafeConfigParser()

    def __init__(self, api_key=None, personal_key=None, history=None,
                 start=None, stop=None, segment=None, section=None,
                 conf_path=None):

        self.section = section or 'defaults'

        # If not set on constructor load api and personal keys from config
        if not (api_key and personal_key):
            conf_path = conf_path or os.path.join(os.path.expanduser('~'),
                                                  '.pyswrve')
            self.__prs.read(conf_path)

            # Check does selected config section exist
            if not (self.__prs.has_section(self.section) and
                    self.__prs.has_section('defaults')):
                print('\
Selected section not found, please set api key and personal key manually')
                return
            elif not self.__prs.has_section(self.section):
                print('Selected section not found, using defaults')
                self.section = 'defaults'

            api_key = self.__prs.get(self.section, 'api_key')
            personal_key = self.__prs.get(self.section, 'personal_key')
        else:
            self.__prs.add_section(self.section)
            self.__prs.set(self.section, 'api_key', api_key)
            self.__prs.set(self.section, 'personal_key', personal_key)

        # Required by any request
        self.defaults = {
            'api_key': api_key,
            'personal_key': personal_key,
            'history': history,
            'start': start,
            'stop': stop,
            'segment': segment
        }

    def __correct_decode(self, lst):
        '''
        Do correct decode of all list items to unicode in python 2
        '''

        res = []
        e = sys.getfilesystemencoding()  # encoding like 'UTF-8'
        for item in lst:
            if type(item) != unicode:
                res.append(item.decode(e))
            else:
                res.append(item)

        return res

    def __prepare_queries(self, q=None, nq=None, in_keys=None,
                          not_in_keys=None, with_keys=False):
        '''
        Prepare queries for parse funcs, convert to lists, decode, etc...
        '''

        if q and type(q) != list:
            q = [q]
        if nq and type(nq) != list:
            nq = [nq]

        # u'КИРИЛЛИЦА' != 'КИРИЛЛИЦА' in Python 2, need str => unicode
        if q and sys.version_info[0] < 3:
            q = self.__correct_decode(q)
        if nq and sys.version_info[0] < 3:
            nq = self.__correct_decode(nq)

        if not with_keys:
            return q, nq
        else:
            if in_keys and type(in_keys) != list:
                in_keys = [in_keys]
            if not_in_keys and type(not_in_keys) != list:
                not_in_keys = [not_in_keys]

            if in_keys and sys.version_info[0] < 3:
                in_keys = self.__correct_decode(in_keys)
            if not_in_keys and sys.version_info[0] < 3:
                not_in_keys = self.__correct_decode(not_in_keys)

            return q, nq, in_keys, not_in_keys

    def __parse_lst_by_query(self, data, q=None, nq=None):
        '''
        Parse list and saves only elements which (not) match with query
        # q - query (or list with them) when item saves if match with query
        # nq - query (ot list with) when item saves if NOT match with query
        Return list
        '''

        q, nq = self.__prepare_queries(q, nq)

        res = []
        if q and nq:  # if both queries were set
            ok_res = []
            bad_res = []
            for item in data:
                for qi in q:  # if item match with query from q
                    if re.findall(qi, item, re.IGNORECASE):
                        ok_res.append(item)  # add to ok_res

                for nqi in nq:  # if match with query from nq
                    if re.findall(nqi, item, re.IGNORECASE):
                        bad_res.append(item)  # add to bad_res

            # Add items from ok_res to res if them not in bad_res
            if bad_res:
                for item in ok_res:
                    if item not in bad_res:
                        res.append(item)
            else:
                res = ok_res

        elif q:  # only q was set
            for item in data:
                for qi in q:  # check with every query from q list
                    if re.findall(qi, item, re.IGNORECASE):
                        res.append(item)

        elif nq:  # only nq was set
            for item in data:
                for nqi in nq:  # check with every query from nq list
                    if not re.findall(nqi, item, re.IGNORECASE):
                        res.append(item)

        return res

    ### --- Options --- ###
    def save_defaults(self):
        ''' Save default params from config file '''

        conf_path = os.path.join(os.path.expanduser('~'), '.pyswrve')
        with open(conf_path, 'w') as f:
            self.__prs.write(f)

    def set_param(self, param, val):
        '''
        Change value of param defined on object creation or set one new
        '''

        if param == 'api_key':
            self.__prs.set(self.section, 'api_key', param)
        elif param == 'personal_key':
            self.__prs.set(self.section, 'personal_key', param)

        self.defaults[param] = val

    def set_dates(self, start=None, stop=None, period=None, period_count=None):
        ''' Set start and stop or history params '''

        if not (start and stop or period):
            print('You need to set start & stop dates or set period')
            return
        elif period:

            # About period & period_count
            # Period = week, period_count = 3 => 3 weeks
            # Period = month, period_count = 5 => 5 months, etc...
            if not period_count:
                period_count = 1
            stop = date.today() - timedelta(days=1)

            if period == 'day':
                count = 1
            elif period == 'week':
                count = 7
            elif period == 'month':
                count = 30
            elif period == 'year':
                count = 365

            start = stop - timedelta(days=count*period_count)

        self.defaults['start'] = str(start)
        self.defaults['stop'] = str(stop)

    ### --- KPI --- ###
    def get_kpi(self, factor, with_date=True, currency=None, params=None,
                tax=None):
        ''' Request KPI factor data from swrve. Return list. '''

        # Request url
        url = 'https://dashboard.swrve.com/api/1/exporter/kpi/%s.json' % factor
        params = params or dict(self.defaults) # request params
        if currency:
            params['currency'] = currency  # cash, coins, etc...

        req = requests.get(url, params=params).json()

        # Request errors
        if type(req) == dict:
            if 'error' in req.keys():
                print('Error: %s' % req['error'])
                return

        if not with_date:  # without date
            if tax and (factor in self.kpi_taxable):  # with tax
                # value * (1 - tax), then round it to 2 symbols after dot
                data = [round(i[1] * (1 - tax), 2) for i in req[0]['data']]
            else:  # results without tax
                data = [i[1] for i in req[0]['data']]
        else:  # with date
            data = req[0]['data']
            if tax and (factor in self.kpi_taxable):
                for i in range(len(data)):
                    if data[i][1]:
                        data[i][1] = round(data[i][1] * (1 - tax), 2)

        return data

    def get_kpi_dau(self, factor, with_date=True, currency=None, params=None,
                    tax=None):
        ''' Request data for KPI factor / DAU (per one user). Return list. '''

        # Request url
        url = 'https://dashboard.swrve.com/api/1/exporter/kpi/%s.json' % factor
        params = params or dict(self.defaults) # request params
        if currency:
            params['currency'] = currency  # cash, coins, etc...

        dau = self.get_kpi('dau', False, currency, params)
        if not dau:  # dau will be None if request was failed with error
            return   # because error already was printed just return
        req = requests.get(url, params=params).json()

        fdata = req[0]['data']  # factor data
        data = []
        if not with_date:  # without date
            for i in range(len(dau)):
                # Check does dau[i] > 0 for ZeroDivisionError fix
                if dau[i]:
                    # Substract tax from value
                    if tax and (factor in self.kpi_taxable):
                        val = round((fdata[i][1] / dau[i]) * (1 - tax), 4)
                    else:  # no substraction
                        val = round(fdata[i][1] / dau[i], 4)
                else:
                    val = 0
                data.append(val)
        else:  # with date
            for i in range(len(dau)):
                if dau[i]:
                    if tax and (factor in self.kpi_taxable):
                        if fdata[i][1]:
                            fdata[i][1] = round((fdata[i][1] / dau[i])*(1-tax),
                                                4)
                    else:
                        fdata[i][1] = round(fdata[i][1] / dau[i], 4)
                else:
                    fdata[i][1] = 0
            data = fdata

        return data

    def get_few_kpi(self, factor_lst, with_date=True, per_user=False,
                    currency=None, params=None, tax=None):
        ''' Request data for few different KPI factors. Return list. '''

        params = params or dict(self.defaults) # request params
        if currency:
            params['currency'] = currency  # cash, coins, etc...

        if per_user:
            get_func = self.get_kpi_dau
        else:
            get_func = self.get_kpi

        count_index = 0
        results = []
        for factor in factor_lst:
            if not count_index:  # == 0

                if with_date:
                    results = get_func(factor, tax=tax)
                else:
                    results = [[i] for i in get_func(factor, False, tax=tax)]
                count_index += 1

            else:  # > 0
                data = get_func(factor, False, tax=tax)
                for i in range(len(data)):
                    results[i] += [data[i]]

        return results

    ### --- Events --- ###
    def get_evt_lst(self, q=None, nq=None, params=None, active_only=None):
        '''
        Request list with all events from swrve
        # q - query when item saves if match with query
        # nq - query when item saves if NOT match with query
        Return list
        '''

        # Request url
        url = 'https://dashboard.swrve.com/api/1/exporter/event/list'
        params = params or dict(self.defaults) # request params

        req = requests.get(url, params=params).json()  # do request
        # Request errors
        if type(req) == dict:
            if 'error' in req.keys():
                print('Error: %s' % req['error'])
                return

        if not (q or nq):  # if not specifed query return all list
            res = req
        else:
            res = self.__parse_lst_by_query(req, q, nq)

        if active_only:  # if set active only check every event
            results = []
            current_seg = self.defaults['segment']
            self.set_param('segment', None)
            for evt in res:
                val = sum(self.get_evt_stat(evt, with_date=False)[evt])
                if val:
                    results.append(evt)
            self.set_param('segment', current_seg)

            return results
        else:
            return res

    def get_payload_lst(self, ename=None, q=None, nq=None, params=None):
        '''
        Request payloads list for event
        # q - query when item saves if match with query
        # nq - query when item saves if NOT match with query
        Return list
        '''

        # Request url
        url = 'https://dashboard.swrve.com/api/1/exporter/event/payloads'
        params = params or dict(self.defaults) # request params
        if ename:
            params['name'] = ename

        req = requests.get(url, params=params).json()  # do request
        # Request errors
        if type(req) == dict:
            if 'error' in req.keys():
                print('Error: %s' % req['error'])
                return

        if not (q or nq):  # if not specifed query return all list
            return req
        else:
            return self.__parse_lst_by_query(req, q, nq)

    def get_evt_stat(self, ename=None, payload=None, payload_val=None,
                     payload_sum=None, with_date=True, per_user=False,
                     params=None):
        '''
        Request events triggering count with(out) payload key. Return dict.
        If with payload, keys are payload's values, else key is an event name.
        '''

        if (payload_val or payload_sum) and not payload:
            print('\
If you use payload value or sum then you need to set payload too')
            return

        params = params or dict(self.defaults) # request params
        if ename:
            params['name'] = ename
        if payload:
            params['payload_key'] = payload

        if payload:
            url = 'https://dashboard.swrve.com/api/1/exporter/event/payload'
        else:
            url = 'https://dashboard.swrve.com/api/1/exporter/event/count'

        req = requests.get(url, params=params).json()  # do request
        # Request errors
        if type(req) == dict:
            if 'error' in req.keys():
                print('Error: %s' % req['error'])
                return

        data = {}
        if payload and payload_val:
            payload_val = str(payload_val)
            for d in req:
                if d['payload_value'] == payload_val:
                    data[payload_val] = d['data']
                    break

        elif payload:  # with payload
            for d in req:
                if with_date:  # key is a payload value
                    data[d['payload_value']] = d['data']
                else:
                    data[d['payload_value']] = [i[1] for i in d['data']]

        else:  # without payload key is an event name
            if not with_date:
                data[req[0]['name']] = [i[1] for i in req[0]['data']]
            else:
                data[req[0]['name']] = req[0]['data']

            if per_user:  # calc for one user
                dau = self.get_kpi('dau', False, params=params)
                key = list(data.keys())[0]  # one element => first key
                for i in range(len(dau)):
                    if not with_date:
                        # Check does dau[i] > 0 for ZeroDivisionError fix
                        if dau[i]:
                            data[key][i] = round(data[key][i] / dau[i], 4)
                        else:
                            data[key][i] = 0
                    else:
                        if dau[i]:
                            data[key][i][1] = round(data[key][i][1] / dau[i],4)
                        else:
                            data[key][i][1] = 0

        # Aggregate payload values
        if payload and payload_sum:
            for key in data:
                val = 0
                if not with_date:
                    for i in data[key]:
                        val += i
                else:
                    for i in data[key]:
                        val += i[1]

                data[key] = val

        return data

    ### --- Items & Resources --- ###
    def get_item_sales(self, item=None, tag=None, currency=None, revenue=True,
                       with_date=True, per_user=False, params=None):
        '''
        Request count of item sales or revenue from items sales
        Return dict where key is 'item name - currency'
        '''

        params = params or dict(self.defaults) # request params
        if item:
            params['uid'] = item
        if tag:
            params['tag'] = tag
        if currency:
            params['currency'] = currency

        if revenue:
            url = 'https://dashboard.swrve.com/api/1/exporter/item/revenue'
        else:
            url = 'https://dashboard.swrve.com/api/1/exporter/item/sales'

        req = requests.get(url, params=params).json()  # do request
        # Request errors
        if type(req) == dict:
            if 'error' in req.keys():
                print('Error: %s' % req['error'])
                return

        data = {}
        for d in req:
            # Key for data dict 'item name - currency'
            k = '%s - %s' % (d['name'], d['currency'])
            if not with_date:
                data[k] = [i[1] for i in d['data']]
            else:
                data[k] = d['data']

        if per_user:  # calc for one user
            dau = self.get_kpi('dau', False, params=params)

            for key in data.keys():
                for i in range(len(dau)):
                    if not with_date:
                        # Check does dau[i] > 0 for ZeroDivisionError fix
                        if dau[i]:
                            data[key][i] = round(data[key][i] / dau[i], 4)
                        else:
                            data[key][i] = 0
                    else:
                        if dau[i]:
                            data[key][i][1] = round(data[key][i][1] / dau[i],4)
                        else:
                            data[key][i][1] = 0

        return data

    ### --- Segments --- ###
    def get_segment_lst(self, q=None, nq=None, params=None, active_only=None):
        '''
        Request list with all segments from swrve
        # q - query when item saves if match with query
        # nq - query when item saves if NOT match with query
        Return list
        '''

        # Request url
        url = 'https://dashboard.swrve.com/api/1/exporter/segment/list'
        params = params or dict(self.defaults) # request params

        req = requests.get(url, params=params).json()  # do request
        # Request errors
        if type(req) == dict:
            if 'error' in req.keys():
                print('Error: %s' % req['error'])
                return

        if not (q or nq):  # if not specifed query return all list
            res = req
        else:
            res = self.__parse_lst_by_query(req, q, nq)

        if active_only:   # if set active only check every
            results = []  # segment activity
            current_seg = self.defaults['segment']
            for seg in res:
                self.set_param('segment', seg)

                val = sum(self.get_kpi('dau', with_date=False))
                if val:
                    results.append(seg)
            self.set_param('segment', current_seg)
            return results
        else:
            return res
