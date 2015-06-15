import smtplib
import tornado.ioloop
import tornado.web
import tornado.httpserver
from tornado.options import define, options
from tornado.escape import url_escape
from tornado.web import (StaticFileHandler, RequestHandler, asynchronous,
                         HTTPError)
from tornado.httpclient import AsyncHTTPClient
from tornado import gen
from os.path import abspath, dirname, join
from jinja2 import Environment, PackageLoader
from sqlalchemy.orm import sessionmaker, aliased, Bundle
from sqlalchemy import create_engine, desc, func, or_
from collections import Counter
import simplejson as json
import subprocess
import os

from bigg2 import queries
from bigg2.queries import NotFoundError
from ome import settings
from ome.models import (Model, Component, Reaction, Compartment, Metabolite,
                        CompartmentalizedComponent, ModelReaction,
                        ReactionMatrix, GeneReactionMatrix,
                        ModelCompartmentalizedComponent, ModelGene, Gene,
                        Comments, GenomeRegion, Genome)
from ome.base import Session
from ome.loading.model_loading.parse import split_compartment
import ome
import datetime

define("port", default= 8888, help="run on given port", type=int)
define("password", default= "", help="password to email", type=str)

# set up jinja2 template location
env = Environment(loader=PackageLoader('bigg2', 'templates'),
                  extensions=['jinja2.ext.with_'])

# root directory
directory = abspath(dirname(__file__))

# api version
api_v = 'v2'
api_host = 'bigg.ucsd.edu'

# make a tutorial on how to make a api request using curl
# http://www.restapitutorial.com/

# -------------------------------------------------------------------------------
# Application API
# -------------------------------------------------------------------------------
def get_application():
    return tornado.web.Application([
        (r'/', MainHandler),
        # 
        # Universal
        #
        (r'/api/%s/(?:models/)?universal/reactions/?$' % api_v, UniversalReactionListHandler),
        (r'/(?:models/)?universal/reactions/?$', UniversalReactionListDisplayHandler),
        # 
        (r'/api/%s/(?:models/)?universal/reactions/([^/]+)/?$' % api_v, UniversalReactionHandler),
        (r'/(?:models/)?universal/reactions/([^/]+)/?$', UniversalReactionDisplayHandler),
        #
        (r'/api/%s/(?:models/)?universal/metabolites/?$' % api_v, UniversalMetaboliteListHandler),
        (r'/(?:models/)?universal/metabolites/?$', UniversalMetaboliteListDisplayHandler),
        # 
        (r'/api/%s/(?:models/)?universal/metabolites/([^/]+)/?$' % api_v, UniversalMetaboliteHandler),
        (r'/(?:models/)?universal/metabolites/([^/]+)/?$', UniversalMetaboliteDisplayHandler),
        # 
        (r'/api/%s/compartments/?$' % api_v, CompartmentListHandler),
        (r'/compartments/?$', CompartmentListDisplayHandler),
        # 
        (r'/api/%s/compartments/([^/]+)/?$' % api_v, CompartmentHandler),
        (r'/compartments/([^/]+)/?$', CompartmentDisplayHandler),
        #
        (r'/api/%s/genomes/?$' % api_v, GenomeListHandler),
        (r'/genomes/?$', GenomeListDisplayHandler),
        # 
        (r'/api/%s/genomes/([^/]+)/?$' % api_v, GenomeHandler),
        (r'/genomes/([^/]+)/?$', GenomeDisplayHandler),
        #
        # By model
        #
        (r'/api/%s/models/?$' % api_v, ModelListHandler),
        (r'/models/?$', ModelsListDisplayHandler),
        #
        (r'/api/%s/models/([^/]+)/?$' % api_v, ModelHandler),
        (r'/models/([^/]+)/?$', ModelDisplayHandler),
        # 
        (r'/(?:api/%s/)?models/([^/]+)/download/?$' % api_v, ModelDownloadHandler),
        #
        (r'/api/%s/models/([^/]+)/reactions/([^/]+)/?$' % api_v, ReactionHandler),
        (r'/models/([^/]+)/reactions/([^/]+)/?$', ReactionDisplayHandler),
        # 
        (r'/api/%s/models/([^/]+)/reactions/?$' % api_v, ReactionListHandler),
        (r'/models/([^/]+)/reactions/?$', ReactionListDisplayHandler),
        #
        (r'/api/%s/models/([^/]+)/metabolites/?$' % api_v, MetaboliteListHandler),
        (r'/models/([^/]+)/metabolites/?$', MetabolitesListDisplayHandler),
        #
        (r'/api/%s/models/([^/]+)/metabolites/([^/]+)/?$' % api_v, MetaboliteHandler),
        (r'/models/([^/]+)/metabolites/([^/]+)/?$', MetaboliteDisplayHandler),
        #
        (r'/api/%s/models/([^/]+)/genes/([^/]+)/?$' % api_v, GeneHandler),
        (r'/models/([^/]+)/genes/([^/]+)/?$', GeneDisplayHandler),
        #
        (r'/api/%s/models/([^/]+)/genes/?$' % api_v, GeneListHandler),
        (r'/models/([^/]+)/genes/?$', GeneListDisplayHandler),
        # 
        # Search
        (r'/api/%s/search$' % api_v, SearchHandler),
        (r'/search$', SearchDisplayHandler),
        (r'/advanced_search$', AdvancedSearchHandler),
        (r'/advanced_search_external_id_results$', AdvancedSearchExternalIDHandler),
        (r'/advanced_search_results$', AdvancedSearchResultsHandler),
        (r'/linkout_advance_search_results$', LinkoutAdvanceSearchResultsHandler),
        (r'/autocomplete$', AutocompleteHandler),
        #
        # Maps
        (r'/escher_map_json/([^/]+)$', EscherMapJSONHandler),
        #
        # Comments
        (r'/submiterror$', SubmitErrorHandler),
        #
        # Pages
        (r'/web_api$', WebAPIHandler),
        (r'/license$', LicenseHandler),
        #
        # Static/Download
        (r'/static/(.*)$', StaticFileHandler, {'path': join(directory, 'static')})
    ], debug=True)

def run(public=True):
    """Run the server"""

    # make sure the indices are ready
    print('Creating pg_trgm extension and indices')
    os.system('psql -d %s -f %s' % (settings.postgres_database, join(directory, 'setup.sql')))

    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(get_application())
    print('serving BiGG 2 on port %d' % options.port)
    http_server.listen(options.port, None if public else "localhost")
    try:
        tornado.ioloop.IOLoop.instance().start()
    except KeyboardInterrupt:
        print("bye!")

def stop():
    """Stop the server"""
    tornado.ioloop.IOLoop.instance().stop()

# -------------------------------------------------------------------------------
# Handlers
# -------------------------------------------------------------------------------

class BaseHandler(RequestHandler):
    pass


class MainHandler(BaseHandler):
    def get(self):
        template = env.get_template('index.html')
        self.write(template.render())
        self.set_header('Content-type','text/html')
        self.finish()


# reactions
class UniversalReactionListHandler(BaseHandler):
    def get(self):
        #column_names = {'0': 'reaction.bigg_id', '1': 'reaction.name', 
        #                '2': 'model.bigg_id', '3': 'genome.organism'}

        # get arguments
        page = self.get_argument('page', None)
        size = self.get_argument('size', None)

        # get the sorting column
        sort_col_index = 0
        sort_direction = 'ascending'
        for k, v in self.request.query_arguments.iteritems():
            # k = 'col[1]'
            split = [x.strip('[]') for x in k.split('[')] 
            # split = ['col', '1']
            if len(split) != 2:
                continue
            if split[0] == 'col':
                sort_col_index = int(split[1])
                sort_direction = ('ascending' if v[0] == '0' else 'descending')

        # run the queries
        session = Session()
        if page is None or size is None:
            result = queries.get_universal_reactions(session)
        else:
            raw_results = queries.get_universal_reactions_pager(page, size, sort_col_index, 
                                                                sort_direction, session)
            table_results = [{'BiGG': '<a href ="/universal/reactions/{0}">{0}</a>'.format(x['bigg_id']),
                              'Name': x['name'], 'Model': 'Universal', 'Organism': '-'}
                              for x in raw_results]
            result = {'rows': table_results,
                      'total_rows': queries.get_universal_reactions_count(session),
                      'headers': ['BiGG', 'Name', 'Model', 'Organism']}

#        if page and int(page) > 0:
 #           import ipdb; ipdb.set_trace()

        # write out the JSON
        data = json.dumps(result)
        self.write(data)
        self.set_header('Content-type', 'application/json')
        self.finish()
        session.close()


class UniversalReactionListDisplayHandler(BaseHandler):
    @asynchronous
    @gen.coroutine
    def get(self):
        template = env.get_template("list_display.html")
        http_client = AsyncHTTPClient()
        url_request = 'http://localhost:%d/api/%s/universal/reactions' % (options.port, api_v)
        request = tornado.httpclient.HTTPRequest(url=url_request,
                                                 connect_timeout=20.0,
                                                 request_timeout=20.0)
        response = yield gen.Task(http_client.fetch, request)
        if response.error:
            raise HTTPError(404)
        dictionary = {'results': {'reactions': [{'bigg_id': r['bigg_id'],
                                                 'name': r['name'],
                                                 'model_bigg_id': 'universal'}
                                                for r in json.loads(response.body)]}}
        self.write(template.render(dictionary)) 
        self.set_header('Content-type','text/html')
        self.finish()


class UniversalReactionHandler(BaseHandler):
    def get(self, reaction_bigg_id):
        session = Session()
        # get the reaction object
        try:
            result = queries.get_reaction_and_models(reaction_bigg_id, session)
        except NotFoundError:
            raise HTTPError(404)
        data = json.dumps(result)
        self.write(data)
        self.set_header('Content-type', 'json')
        self.finish()
            

class UniversalReactionDisplayHandler(BaseHandler):
    @asynchronous
    @gen.coroutine
    def get(self, reaction_bigg_id):
        template = env.get_template("universal_reaction.html")
        http_client = AsyncHTTPClient()
        url_request = ('http://localhost:%d/api/%s/models/universal/reactions/%s' %
                       (options.port, api_v, url_escape(reaction_bigg_id, plus=False)))
        request = tornado.httpclient.HTTPRequest(url=url_request,
                                                 connect_timeout=20.0,
                                                 request_timeout=20.0)
        response = yield gen.Task(http_client.fetch, request)
        if response.error:
            raise HTTPError(404)
        results = json.loads(response.body)
        self.write(template.render(results))
        self.set_header('Content-type','text/html')
        self.finish()  


class UniversalMetaboliteListHandler(BaseHandler):
    def get(self):
        """session = Session()
        metabolites = [{'bigg_id': x[0], 'name': x[1]}
                       for x in session.query(Metabolite.bigg_id, Metabolite.name).all()]
        data = json.dumps(sorted(metabolites, key=lambda m: m['bigg_id'].lower()))"""

        page = self.get_argument('page', None)
        size = self.get_argument('size', None)

        # get the sorting column
        sort_col_index = 0
        sort_direction = 'ascending'
        for k, v in self.request.query_arguments.iteritems():
            # k = 'col[1]'
            split = [x.strip('[]') for x in k.split('[')] 
            # split = ['col', '1']
            if len(split) != 2:
                continue
            if split[0] == 'col':
                sort_col_index = int(split[1])
                sort_direction = ('ascending' if v[0] == '0' else 'descending')

        # run the queries
        session = Session()
        if page is None or size is None:
            result = queries.get_universal_metabolites(session)
        else:
            raw_results = queries.get_universal_metabolites_pager(page, size, sort_col_index, 
                                                                sort_direction, session)
            table_results = [{'BiGG': '<a href ="/universal/metabolites/{0}">{0}</a>'.format(x['bigg_id']),
                              'Name': x['name'], 'Model': 'Universal', 'Organism': '-'}
                              for x in raw_results]
            result = {'rows': table_results,
                      'total_rows': queries.get_universal_metabolites_count(session),
                      'headers': ['BiGG', 'Name', 'Model', 'Organism']}
        
        session.close()
        data = json.dumps(result)
        self.write(data)
        self.set_header('Content-type', 'application/json')
        self.finish()
        
        
class UniversalMetaboliteListDisplayHandler(BaseHandler):
    @asynchronous
    @gen.coroutine
    def get(self):
        template = env.get_template("list_display.html")
        http_client = AsyncHTTPClient()
        url_request = 'http://localhost:%d/api/%s/universal/metabolites' % \
                      (options.port, api_v)
        request = tornado.httpclient.HTTPRequest(url=url_request,
                                                 connect_timeout=20.0,
                                                 request_timeout=20.0)
        response = yield gen.Task(http_client.fetch, request)
        if response.error:
            raise HTTPError(404)
        template_data = {'results': {'metabolites': [{'bigg_id': r['bigg_id'],
                                                      'name': r['name'],
                                                      'model_bigg_id': 'universal'}
                                                     for r in json.loads(response.body)]}}
        self.write(template.render(template_data)) 
        self.set_header('Content-type','text/html')
        self.finish()
        

class UniversalMetaboliteHandler(BaseHandler):
    def get(self, met_bigg_id):
        session = Session()
        results = queries.get_metabolite(met_bigg_id, session)
        session.close()            

        data = json.dumps(results)
        self.write(data)
        self.set_header('Content-type', 'application/json')
        self.finish()


class UniversalMetaboliteDisplayHandler(BaseHandler):
    @asynchronous
    @gen.coroutine
    def get(self, met_bigg_id):
        template = env.get_template("universal_metabolite.html")
        http_client = AsyncHTTPClient()
        url_request = 'http://localhost:%d/api/%s/models/universal/metabolites/%s' % \
                      (options.port, api_v, url_escape(met_bigg_id, plus=False))
        response = yield gen.Task(http_client.fetch, url_request)
        if response.error:
            raise HTTPError(404)
        results = json.loads(response.body)
        self.write(template.render(results))
        self.set_header('Content-type','text/html')
        self.finish()   
              

class ReactionListHandler(BaseHandler):
    def get(self, model_bigg_id):
                #column_names = {'0': 'reaction.bigg_id', '1': 'reaction.name', 
        #                '2': 'model.bigg_id', '3': 'genome.organism'}

        # get arguments
        page = self.get_argument('page', None)
        size = self.get_argument('size', None)

        # get the sorting column
        sort_col_index = 0
        sort_direction = 'ascending'
        for k, v in self.request.query_arguments.iteritems():
            # k = 'col[1]'
            split = [x.strip('[]') for x in k.split('[')] 
            # split = ['col', '1']
            if len(split) != 2:
                continue
            if split[0] == 'col':
                sort_col_index = int(split[1])
                sort_direction = ('ascending' if v[0] == '0' else 'descending')

        # run the queries
        session = Session()
        if page is None or size is None:
            result = queries.get_reactions_for_model(model_bigg_id, session)
            sorted(result, key=lambda r: r['bigg_id'].lower())
        else:
            raw_results = queries.get_reactions_pager(page, size, sort_col_index, 
                                                                sort_direction,  model_bigg_id, session)
            table_results = [{'BiGG': '<a href ="/models/{0}/reactions/{1}">{1}</a>'.format(x['model_bigg_id'], x['bigg_id']),
                              'Name': x['name'], 'Model': x['model_bigg_id'], 'Organism': x['organism']}
                              for x in raw_results]
            result = {'rows': table_results,
                      'total_rows': queries.get_reactions_count(model_bigg_id, session),
                      'headers': ['BiGG', 'Name', 'Model', 'Organism']}
        
        session.close()
        self.write(json.dumps(result))
        self.set_header('Content-type', 'json')
        self.finish()   
        
        
class ReactionListDisplayHandler(BaseHandler):
    @asynchronous
    @gen.coroutine
    def get(self, model_bigg_id):
        template = env.get_template("list_display.html")
        http_client = AsyncHTTPClient()
        url_request = ('http://localhost:%d/api/%s/models/%s/reactions' %
                       (options.port, api_v, url_escape(model_bigg_id, plus=False)))
        request = tornado.httpclient.HTTPRequest(url=url_request,
                                                 connect_timeout=20.0,
                                                 request_timeout=20.0)
        response = yield gen.Task(http_client.fetch, request)
        if response.error:
            raise HTTPError(404)
        response_data = json.loads(response.body)
        template_data = {'results': {'reactions': [{'model_bigg_id': model_bigg_id,
                                                    'bigg_id': x['bigg_id'],
                                                    'name': x['name'],
                                                    'organism': x['organism']}
                                                   for x in response_data]}}
        self.write(template.render(template_data)) 
        self.set_header('Content-type','text/html')
        self.finish()


class ReactionHandler(BaseHandler):
    def get(self, model_bigg_id, reaction_bigg_id):
        session = Session()
        results = queries.get_model_reaction(model_bigg_id, reaction_bigg_id,
                                             session)
        session.close()

        data = json.dumps(results)
        self.write(data)
        self.set_header('Content-type', 'application/json')
        self.finish()
        

class ReactionDisplayHandler(BaseHandler):
    @asynchronous
    @gen.coroutine
    def get(self, model_bigg_id, reaction_bigg_id):
        template = env.get_template("reaction.html")
        http_client = AsyncHTTPClient()
        url_request = 'http://localhost:%d/api/%s/models/%s/reactions/%s' % \
                      (options.port, api_v,
                       url_escape(model_bigg_id, plus=False),
                       url_escape(reaction_bigg_id, plus=False))
        request = tornado.httpclient.HTTPRequest(url=url_request,
                                                 connect_timeout=20.0,
                                                 request_timeout=20.0)
        response = yield gen.Task(http_client.fetch, request)
        if response.error:
            raise HTTPError(404)
        data = json.loads(response.body)
        for result in data['results']:
            result['reaction_string'] = queries.build_reaction_string(data['metabolites'],
                                                                      result['lower_bound'],
                                                                      result['upper_bound'])
        self.write(template.render(data)) 
        self.set_header('Content-type','text/html')
        self.finish() 


# Compartments
class CompartmentListHandler(BaseHandler):
    def get(self):
        session = Session()
        results = [{'bigg_id': x[0], 'name': x[1]}
                   for x in session.query(Compartment.bigg_id, Compartment.name).all()]
        data = json.dumps(results)
        self.write(data)
        self.set_header('Content-type', 'application/json')
        self.finish()
        session.close()   


class CompartmentListDisplayHandler(BaseHandler):
    @asynchronous
    @gen.coroutine
    def get(self):
        template = env.get_template("compartments.html")
        http_client = AsyncHTTPClient()
        url_request = 'http://localhost:%d/api/%s/compartments' % (options.port, api_v)
        request = tornado.httpclient.HTTPRequest(url=url_request,
                                                 connect_timeout=20.0,
                                                 request_timeout=20.0)
        response = yield gen.Task(http_client.fetch, request)
        if response.error:
            raise HTTPError(404)
        results = json.loads(response.body)
        self.write(template.render({'compartments': results})) 
        self.set_header('Content-type','text/html')
        self.finish()


class CompartmentHandler(BaseHandler):
    def get(self, compartment_bigg_id):
        session = Session()
        result_db = (session
                     .query(Compartment)
                     .filter(Compartment.bigg_id == compartment_bigg_id)
                     .first())
        result = {'bigg_id': result_db.bigg_id, 'name': result_db.name}
        data = json.dumps(result)
        self.write(data)
        self.set_header('Content-type', 'application/json')
        self.finish()
        session.close()


class CompartmentDisplayHandler(BaseHandler):
    @asynchronous
    @gen.coroutine
    def get(self, compartment_bigg_id):
        template = env.get_template("compartment.html")
        http_client = AsyncHTTPClient()
        url_request = 'http://localhost:%d/api/%s/compartments/%s' % \
                      (options.port, api_v,
                       url_escape(compartment_bigg_id, plus=False))
        request = tornado.httpclient.HTTPRequest(url=url_request,
                                                 connect_timeout=20.0,
                                                 request_timeout=20.0)
        response = yield gen.Task(http_client.fetch, request)
        if response.error:
            raise HTTPError(404)
        results = json.loads(response.body)
        self.write(template.render(results)) 
        self.set_header('Content-type','text/html')
        self.finish()
        

# Genomes
class GenomeListHandler(BaseHandler):
    def get(self):
        session = Session()
        results = [{'bioproject_id': x[0], 'organism': x[1]}
                   for x in session.query(Genome.bioproject_id, Genome.organism).all()]
        data = json.dumps(results)
        self.write(data)
        self.set_header('Content-type', 'application/json')
        self.finish()
        session.close()   


class GenomeListDisplayHandler(BaseHandler):
    @asynchronous
    @gen.coroutine
    def get(self):
        template = env.get_template("genomes.html")
        http_client = AsyncHTTPClient()
        url_request = 'http://localhost:%d/api/%s/genomes' % (options.port, api_v)
        request = tornado.httpclient.HTTPRequest(url=url_request,
                                                 connect_timeout=20.0,
                                                 request_timeout=20.0)
        response = yield gen.Task(http_client.fetch, request)
        if response.error:
            raise HTTPError(404)
        results = json.loads(response.body)
        self.write(template.render({'genomes': results})) 
        self.set_header('Content-type','text/html')
        self.finish()


class GenomeHandler(BaseHandler):
    def get(self, bioproject_id):
        session = Session()
        result = queries.get_genome_and_models(session, bioproject_id)
        data = json.dumps(result)
        self.write(data)
        self.set_header('Content-type', 'application/json')
        self.finish()
        session.close()


class GenomeDisplayHandler(BaseHandler):
    @asynchronous
    @gen.coroutine
    def get(self, bioproject_id):
        template = env.get_template("genome.html")
        http_client = AsyncHTTPClient()
        url_request = 'http://localhost:%d/api/%s/genomes/%s' % \
                      (options.port, api_v, url_escape(bioproject_id, plus=False))
        request = tornado.httpclient.HTTPRequest(url=url_request,
                                                 connect_timeout=20.0,
                                                 request_timeout=20.0)
        response = yield gen.Task(http_client.fetch, request)
        if response.error:
            raise HTTPError(404)
        results = json.loads(response.body)
        self.write(template.render(results)) 
        self.set_header('Content-type','text/html')
        self.finish()


# Models
class ModelListHandler(BaseHandler):    
    def get(self):
        page = self.get_argument('page', None)
        size = self.get_argument('size', None)

        # get the sorting column
        sort_col_index = 0
        sort_direction = 'ascending'
        for k, v in self.request.query_arguments.iteritems():
            # k = 'col[1]'
            split = [x.strip('[]') for x in k.split('[')] 
            # split = ['col', '1']
            if len(split) != 2:
                continue
            if split[0] == 'col':
                sort_col_index = int(split[1])
                sort_direction = ('ascending' if v[0] == '0' else 'descending')

        # run the queries
        session = Session()
        if page is None or size is None:
            result = queries.get_model_list_and_counts(session)
            sorted(result, key=lambda r: r['bigg_id'].lower())
        else:
            raw_results = queries.get_models_pager(page, size, sort_col_index, 
                                                                sort_direction, session)
            table_results = [{'BiGG': '<a href ="/models/{0}">{0}</a>'.format(x['bigg_id']),
                              'Organism': x['organism'], 'Metabolites': '<a href="/models/{0}/metabolites">{1}</a>'.format(x['bigg_id'],x['metabolite_count']), 'Reactions': '<a href="/models/{0}/reactions">{1}</a>'.format(x['bigg_id'], x['reaction_count']), 'Genes': '<a href="/models/{0}/genes">{1}</a>'.format(x['bigg_id'], x['gene_count'])}
                              for x in raw_results]
            result = {'rows': table_results,
                      'total_rows': queries.get_models_count(session),
                      'headers': ['BiGG', 'Organism', 'Metabolites', 'Reactions', 'Genes']}
        session.close()
        data = json.dumps(result)
        self.write(data)
        self.set_header('Content-type', 'application/json')
        self.finish()


class ModelsListDisplayHandler(BaseHandler):
    @asynchronous
    @gen.coroutine
    def get(self):
        template = env.get_template("list_display.html")
        http_client = AsyncHTTPClient()
        url_request = 'http://localhost:%d/api/%s/models' % (options.port, api_v)
        request = tornado.httpclient.HTTPRequest(url=url_request,
                                                 connect_timeout=20.0,
                                                 request_timeout=20.0)
        response = yield gen.Task(http_client.fetch, request)
        if response.error:
            raise HTTPError(404)
        template_data = {'results': {'models': json.loads(response.body)}}
        self.write(template.render(template_data)) 
        self.set_header('Content-type','text/html')
        self.finish()


class ModelDownloadHandler(BaseHandler):
    def get(self, model_bigg_id):
        data = queries.get_model_json_string(model_bigg_id)
        self.write(data)
        self.set_header('Content-type', 'application/json')
        self.finish()


class ModelHandler(BaseHandler):
    def get(self, model_bigg_id):
        session = Session()
        result = queries.get_model_and_counts(model_bigg_id, session)
        session.close()

        data = json.dumps(result)
        self.write(data)
        self.set_header('Content-type', 'application/json')
        self.finish()


class ModelDisplayHandler(BaseHandler):
    @asynchronous
    @gen.coroutine
    def get(self, model_bigg_id):
        template = env.get_template("model.html")
        http_client = AsyncHTTPClient()
        url_request = 'http://localhost:%d/api/%s/models/%s' % \
                      (options.port, api_v, url_escape(model_bigg_id, plus=False))
        print url_request
        request = tornado.httpclient.HTTPRequest(url=url_request,
                                                 connect_timeout=20.0,
                                                 request_timeout=20.0)
        response = yield gen.Task(http_client.fetch, request)
        if response.error:
            raise HTTPError(404)
        results = json.loads(response.body)
        self.write(template.render(results))
        self.set_header('Content-type','text/html')
        self.finish() 
            

class MetaboliteListHandler(BaseHandler):
    def get(self, model_bigg_id):
        page = self.get_argument('page', None)
        size = self.get_argument('size', None)

        # get the sorting column
        sort_col_index = 0
        sort_direction = 'ascending'
        for k, v in self.request.query_arguments.iteritems():
            # k = 'col[1]'
            split = [x.strip('[]') for x in k.split('[')] 
            # split = ['col', '1']
            if len(split) != 2:
                continue
            if split[0] == 'col':
                sort_col_index = int(split[1])
                sort_direction = ('ascending' if v[0] == '0' else 'descending')

        # run the queries
        session = Session()
        if page is None or size is None:
            result = queries.get_metabolites_for_model(model_bigg_id, session)
            sorted(result, key=lambda r: r['bigg_id'].lower())
        else:
            raw_results = queries.get_metabolites_pager(page, size, sort_col_index, 
                                                                sort_direction,  model_bigg_id, session)
            table_results = [{'BiGG': '<a href ="/models/{0}/metabolites/{1}_{2}">{1}_{2}</a>'.format(x['model_bigg_id'], x['bigg_id'], x['compartment']),
                              'Name': x['name'], 'Model': x['model_bigg_id'], 'Organism': x['organism']}
                              for x in raw_results]
            result = {'rows': table_results,
                      'total_rows': queries.get_metabolites_count(model_bigg_id, session),
                      'headers': ['BiGG', 'Name', 'Model', 'Organism']}
        session.close()
        data = json.dumps(result)
        self.write(data)
        self.set_header('Content-type', 'application/json')
        self.finish()
        
        
class MetabolitesListDisplayHandler(BaseHandler):
    @asynchronous
    @gen.coroutine
    def get(self, model_bigg_id):
        template = env.get_template("list_display.html")
        http_client = AsyncHTTPClient()
        url_request = 'http://localhost:%d/api/%s/models/%s/metabolites' % \
                      (options.port, api_v, url_escape(model_bigg_id, plus=False))
        request = tornado.httpclient.HTTPRequest(url=url_request,
                                                 connect_timeout=20.0,
                                                 request_timeout=20.0)
        response = yield gen.Task(http_client.fetch, request)
        if response.error:
            raise HTTPError(404)
        dictionary = {"results": {"metabolites": json.loads(response.body)}}
        self.write(template.render(dictionary)) 
        self.set_header('Content-type','text/html')
        self.finish()
 

class MetaboliteHandler(BaseHandler):
    def get(self, model_bigg_id, comp_met_id):
        session = Session()
        met_bigg_id, compartment_bigg_id = split_compartment(comp_met_id)
        results = queries.get_model_comp_metabolite(met_bigg_id, compartment_bigg_id,
                                                    model_bigg_id, session)
        session.close()
        data = json.dumps(results)
        self.write(data)
        self.set_header('Content-type', 'application/json')
        self.finish()
        

class MetaboliteDisplayHandler(BaseHandler):
    @asynchronous
    @gen.coroutine
    def get(self, model_id, met_bigg_id):
        template = env.get_template("metabolite.html")
        http_client = AsyncHTTPClient()
        url_request = 'http://localhost:%d/api/%s/models/%s/metabolites/%s' % \
                      (options.port, api_v,
                       url_escape(model_id, plus=False),
                       url_escape(met_bigg_id, plus=False))
        request = tornado.httpclient.HTTPRequest(url=url_request,
                                                 connect_timeout=20.0,
                                                 request_timeout=20.0)
        response = yield gen.Task(http_client.fetch, request)
        if response.error:
            raise HTTPError(404)
        results = json.loads(response.body)
        self.write(template.render(results))
        self.set_header('Content-type','text/html')
        self.finish()   


class GeneListHandler(BaseHandler):
    def get(self, model_bigg_id):
        page = self.get_argument('page', None)
        size = self.get_argument('size', None)

        # get the sorting column
        sort_col_index = 0
        sort_direction = 'ascending'
        for k, v in self.request.query_arguments.iteritems():
            # k = 'col[1]'
            split = [x.strip('[]') for x in k.split('[')] 
            # split = ['col', '1']
            if len(split) != 2:
                continue
            if split[0] == 'col':
                sort_col_index = int(split[1])
                sort_direction = ('ascending' if v[0] == '0' else 'descending')

        # run the queries
        session = Session()
        if page is None or size is None:
            result = queries.get_gene_list_for_model(model_bigg_id, session)
            sorted(result, key=lambda s: s['bigg_id'].lower())
        else:
            raw_results = queries.get_genes_pager(page, size, sort_col_index, 
                                                                sort_direction,  model_bigg_id, session)
            table_results = [{'BiGG': '<a href ="/models/{0}/genes/{1}">{1}</a>'.format(x['model_bigg_id'], x['bigg_id']),
                              'Name': x['name'], 'Model': x['model_bigg_id'], 'Organism': x['organism']}
                              for x in raw_results]
            result = {'rows': table_results,
                      'total_rows': queries.get_genes_count(model_bigg_id, session),
                      'headers': ['BiGG', 'Name', 'Model', 'Organism']}
        session.close()
        data = json.dumps(result)
        self.write(data)
        self.set_header('Content-type', 'application/json')
        self.finish()


class GeneListDisplayHandler(BaseHandler):
    @asynchronous
    @gen.coroutine
    def get(self, model_bigg_id):
        template = env.get_template("list_display.html")
        http_client = AsyncHTTPClient()
        url_request = 'http://localhost:%d/api/%s/models/%s/genes' % \
                      (options.port, api_v, url_escape(model_bigg_id, plus=False))
        request = tornado.httpclient.HTTPRequest(url=url_request,
                                                 connect_timeout=20.0,
                                                 request_timeout=20.0)
        response = yield gen.Task(http_client.fetch, request)
        if response.error:
            raise HTTPError(404)
        template_data = {'results': {'genes': json.loads(response.body)}}
        self.write(template.render(template_data))
        self.set_header('Content-type','text/html') 
        self.finish()

 
class GeneHandler(BaseHandler):
    def get(self, model_bigg_id, gene_bigg_id):
        session = Session()
        result= queries.get_model_gene(gene_bigg_id, model_bigg_id, session)
        
        session.close()

        data = json.dumps(result)
        self.write(data)
        self.set_header('Content-type', 'application/json')
        self.finish()


class GeneDisplayHandler(BaseHandler):
    @asynchronous
    @gen.coroutine
    def get(self, model_bigg_id, gene_bigg_id):
        template = env.get_template("gene.html")
        http_client = AsyncHTTPClient()
        url_request = 'http://localhost:%d/api/%s/models/%s/genes/%s' % \
                      (options.port, api_v,
                       url_escape(model_bigg_id, plus=False),
                       url_escape(gene_bigg_id, plus=False))
        request = tornado.httpclient.HTTPRequest(url=url_request,
                                                 connect_timeout=20.0,
                                                 request_timeout=20.0)
        response = yield gen.Task(http_client.fetch, request)
        if response.error:
            raise HTTPError(404)
        results = json.loads(response.body)
        self.write(template.render(results))
        self.set_header('Content-type','text/html')
        self.finish() 
        

class SearchHandler(BaseHandler):
    def get(self):
        query_string = self.get_argument("query")
        page = self.get_argument('page', None)
        size = self.get_argument('size', None)
        searchType = self.get_argument('cPage', None)
        sort_col_index = 0
        sort_direction = 'ascending'
        for k, v in self.request.query_arguments.iteritems():
            # k = 'col[1]'
            split = [x.strip('[]') for x in k.split('[')] 
            # split = ['col', '1']
            if len(split) != 2:
                continue
            if split[0] == 'col':
                sort_col_index = int(split[1])
                sort_direction = ('ascending' if v[0] == '0' else 'descending')

        # run the queries
        session = Session()      
        if page is None or size is None or searchType is None:
                    # genes
            gene_list = queries.search_for_genes(query_string, session)
            
            # reactions
             
            reaction_list = queries.search_for_universal_reactions(query_string,
                                                                   session)
            # metabolites
            metabolite_list = []
            metabolite_list += queries.search_for_universal_metabolites(query_string,
                                                                        session)
            metabolite_list += queries.search_for_metabolites(query_string, session,
                                                              strict=True)
            # models
            
            model_list = queries.search_for_models(query_string, session)
            result = {"results": {"reactions": reaction_list, 
                                  "metabolites": metabolite_list,
                                  "models": model_list,
                                  "genes": gene_list}}
        else:
             # genes
            gene_list = queries.search_for_genes_pager(query_string, page, size, sort_col_index, sort_direction, session)
            
            # reactions
             
            reaction_list = queries.search_for_universal_reactions_pager(query_string,
                                                                   page,
                                                                   size,
                                                                   sort_col_index, 
                                                                   sort_direction,
                                                                   session)
            # metabolites
            metabolite_list = []
            metabolite_list += queries.search_for_universal_metabolites_pager(query_string,
                                                                        page,
                                                                        size,
                                                                        sort_col_index,
                                                                        sort_direction,
                                                                        session)
            metabolite_list += queries.search_for_metabolites_pager(query_string,
                                                              page,
                                                              size,
                                                              sort_col_index,
                                                              sort_direction,
                                                              session,
                                                              strict=True)
        # models
        
            model_list = queries.search_for_models_pager(query_string, page, size, sort_col_index, sort_direction, session)
            
            if (searchType == 'reactions'):
                table_results = [{'BiGG': '<a href ="/models/{0}/reactions/{1}">{1}</a>'.format(x['model_bigg_id'], x['bigg_id']),
                                'Name': x['name'], 'Model': 'universal', 'Organism': '-'}
                                for x in reaction_list]
                result = {'rows': table_results,
                         'total_rows': len(table_results),
                         'headers': ['BiGG', 'Name', 'Model', 'Organism']}
            elif (searchType == 'metabolites'):
                table_results = [{'BiGG': '<a href ="/models/{0}/metabolites/{1}">{1}</a>'.format(x['model_bigg_id'], x['bigg_id']),
                                'Name': x['name'], 'Model': x['model_bigg_id'], 'Organism': x['organism']}
                                for x in metabolite_list]
                result = {'rows': table_results,
                         'total_rows': len(table_results),
                         'headers': ['BiGG', 'Name', 'Model', 'Organism']}
            elif (searchType == 'genes'):
                table_results = [{'BiGG': '<a href ="/models/{0}/genes/{1}">{1}</a>'.format(x['model_bigg_id'], x['bigg_id']),
                                'Name': x['name'], 'Model': x['model_bigg_id'], 'Organism': x['organism']}
                                for x in gene_list]
                result = {'rows': table_results,
                         'total_rows': len(table_results),
                         'headers': ['BiGG', 'Name', 'Model', 'Organism']}
            elif (searchType == 'models'):
                table_results = [{'BiGG': '<a href ="/models/{0}">{0}</a>'.format(x['bigg_id']),
                                'Organism': x['organism'], 'Metabolites': '<a href="/models/{0}/metabolites">{1}</a>'.format(x['bigg_id'],x['metabolite_count']), 'Reactions': '<a href="/models/{0}/reactions">{1}</a>'.format(x['bigg_id'], x['reaction_count']), 'Genes': '<a href="/models/{0}/genes">{1}</a>'.format(x['bigg_id'], x['gene_count'])}
                                for x in model_list]
                result = {'rows': table_results,
                         'total_rows': len(table_results),
                         'headers': ['BiGG', 'Organism', 'Metabolites', 'Reactions', 'Genes']}
        session.close()
        data = json.dumps(result)
        self.write(data) 
        self.set_header('Content-type', 'application/json')
        self.finish()

class SearchDisplayHandler(BaseHandler):
    @asynchronous
    @gen.coroutine
    def get(self):
        template = env.get_template("list_display.html")
        http_client = AsyncHTTPClient()
        query_url = url_escape(self.get_argument("query"), plus=True)
        url_request = ('http://localhost:%d/api/%s/search?query=%s' %
                       (options.port, api_v, query_url))
        request = tornado.httpclient.HTTPRequest(url=url_request,
                                                 connect_timeout=20.0,
                                                 request_timeout=20.0)
        response = yield gen.Task(http_client.fetch, request)
        if response.error:
            raise HTTPError(404)
        template_data = json.loads(response.body)
        self.write(template.render(template_data))
        self.set_header('Content-type','text/html')
        self.finish() 
    

class AdvancedSearchHandler(BaseHandler):
    def get(self):
        template = env.get_template('advanced_search.html')
        session = Session()
        model_list = queries.get_model_list(session)
        database_sources = queries.get_database_sources(session)
        session.close()

        self.write(template.render({'models': model_list,
                                    'database_sources': database_sources}))
        self.set_header('Content-type','text/html') 
        self.finish()

class LinkoutAdvanceSearchResultsHandler(BaseHandler):
    def post(self):
        template = env.get_template("list_display.html")
        #query_strings = [x.strip() for x in self.get_argument('query', '').split(',') if x != '']
        query_string = self.get_argument('query', '')
        external_id = self.get_argument("linkout_choice", None)
        reaction_results = []
        metabolite_results = []
        gene_results = []
        session = Session()
        metabolite_results += queries.search_for_metabolites_by_external_id(query_string, external_id, session)
        dictionary = {'results': {'reactions': reaction_results, 
                                  'metabolites': metabolite_results, 
                                  'genes': gene_results}}

        self.write(template.render(dictionary)) 
        self.set_header('Content-type','text/html')
        self.finish()

class AdvancedSearchExternalIDHandler(BaseHandler):
    def post(self):
        query_string = self.get_argument('query', '')
        database_source = self.get_argument('database_source', '')
        session = Session()
        metabolites = queries.get_metabolites_for_database_id(session,
                                                              query_string,
                                                              database_source)
        session.close()
        dictionary = {'results': {'metabolites': metabolites}}
        
        template = env.get_template("list_display.html")
        self.write(template.render(dictionary)) 
        self.set_header('Content-type','text/html')
        self.finish() 

class AdvancedSearchResultsHandler(BaseHandler):
    def post(self):
        query_strings = [x.strip() for x in
                         self.get_argument('query', '').split(',')
                         if x != '']
        # run the queries
        session = Session()
        def checkbox_arg(name):
            return self.get_argument(name, None) == 'on'

        
        all_models = queries.get_model_list(session)
        model_list = [m for m in all_models if checkbox_arg(m)]
        include_metabolites = checkbox_arg('include_metabolites')
        include_reactions = checkbox_arg('include_reactions')
        include_genes = checkbox_arg('include_genes')
        metabolite_results = []
        reaction_results = []
        gene_results = []

        # genes
        for query_string in query_strings:
            if include_genes:
                gene_results += queries.search_for_genes(query_string, session,
                                                         limit_models=model_list)
            if include_reactions:
                reaction_results += queries.search_for_reactions(query_string, session,
                                                                 limit_models=model_list)
            if include_metabolites:
                metabolite_results += queries.search_for_metabolites(query_string, session,
                                                                     limit_models=model_list)
        result = {'results': {'reactions': reaction_results, 
                              'metabolites': metabolite_results, 
                              'genes': gene_results},
                  'no_pager': True}
        
        session.close()
        template = env.get_template("list_display.html")
        self.write(template.render(result)) 
        self.set_header('Content-type','text/html')
        self.finish() 


class AutocompleteHandler(BaseHandler):
    def get(self):
        query_string = self.get_argument("query") 

        # get the session
        session = Session()
        result_array = queries.search_ids_fast(query_string, session)
        session.close()       

        self.write(json.dumps(result_array))
        self.set_header('Content-type', 'application/json')
        self.finish()

class EscherMapJSONHandler(BaseHandler):
    def get(self, map_name):
        session = Session()
        map_json = queries.json_for_map(map_name, session)
        session.close()       
        
        self.write(map_json)
        self.set_header('Content-type', 'application/json')
        self.finish()


class SubmitErrorHandler(BaseHandler):
    def post(self):
        session = Session()
        useremail = self.get_argument("email", "empty")
        comments = self.get_argument("comments", "empty")
        type = self.get_argument("type", "empty")
        weburl = self.get_argument("url", "empty")
        now = datetime.datetime.now()
        commentobject = Comments(email = useremail, text = comments, date_created = now, type = type, url = weburl)
        session.add(commentobject)
        session.commit()
        session.close()
             

class WebAPIHandler(BaseHandler):
    def get(self):
        template = env.get_template('web_api.html')
        self.write(template.render(api_host=api_host))
        self.set_header('Content-type','text/html')
        self.finish()


class LicenseHandler(BaseHandler):
    def get(self):
        template = env.get_template('about_license_page.html')
        self.write(template.render())
        self.set_header('Content-type','text/html')
        self.finish()


if __name__ == "__main__":
    run()   
