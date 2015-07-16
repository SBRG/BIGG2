from bigg2.queries import *
from bigg2.queries import _shorten_name

from ome import base

from decimal import Decimal
import pytest
from pytest import raises
import time
import json


@pytest.fixture(scope='function')
def session(request):
    """Make a session"""
    def teardown():
        base.Session.close_all()
    request.addfinalizer(teardown)

    return base.Session()

# util
def test__shorten_name():
    assert _shorten_name(None) is None
    assert _shorten_name('abc', 2) == 'ab...'

# Reactions
def test_get_reaction_and_models(session):
    result = get_reaction_and_models('ADA', session)
    assert result['bigg_id'] == 'ADA'
    assert result['name'] == 'Adenosine deaminase'
    assert result['pseudoreaction'] is False
    assert {'bigg_id': 'iAPECO1_1312', 'organism': 'Escherichia coli APEC O1'} \
        in result['models_containing_reaction']
    with raises(Exception):
        result = get_reaction_and_models('not_a_reaction', session)
    

def test_get_reactions_for_model():
    session = base.Session()
    result = get_reactions_for_model('iAPECO1_1312', session)
    assert len(result) > 5
    assert 'ADA' in [x['bigg_id'] for x in result]
    assert 'url' in results[0]
    session.close()
    

def test_get_model_reaction(session):
    result = get_model_reaction('iAPECO1_1312', 'ADA', session)
    assert result['bigg_id'] == 'ADA'
    assert result['name'] == 'Adenosine deaminase'
    assert result['results'][0]['gene_reaction_rule'] == 'APECO1_706'
    assert 'APECO1_706' in [x['bigg_id'] for x in result['results'][0]['genes']]
    assert 'nh4' in [x['bigg_id'] for x in result['metabolites']]
    assert 'Ammonium' in [x['name'] for x in result['metabolites']]
    assert 'c' in [x['compartment_bigg_id'] for x in result['metabolites']]
    assert Decimal(1) in [x['stoichiometry'] for x in result['metabolites']]
    assert 'other_models_with_reaction' in result
    assert 'iAPECO1_1312' not in result['other_models_with_reaction']
    assert 'upper_bound' in result['results'][0]
    assert 'lower_bound' in result['results'][0]
    assert 'objective_coefficient' in result['results'][0]

    
# Models
def test_get_model_list_and_counts():
    session = base.Session()
    result = get_model_list_and_counts(session)
    assert 'iAPECO1_1312' in [r['bigg_id'] for r in result]
    assert 'Escherichia coli APEC O1' in [r['organism'] for r in result]
    assert type(result[0]['metabolite_count']) is int
    assert type(result[0]['reaction_count']) is int
    assert type(result[0]['gene_count']) is int
    assert 'url' in results[0]
    session.close()

def test_get_model_and_counts():
    session = base.Session()
    result = get_model_and_counts('iAPECO1_1312', session)
    assert result['bigg_id'] == 'iAPECO1_1312'
    assert result['organism'] == 'Escherichia coli APEC O1'
    assert type(result['metabolite_count']) is int
    assert type(result['reaction_count']) is int
    assert type(result['gene_count']) is int
    session.close()


def test_get_model_json_string():
    with pytest.raises(NotFoundError):
        get_model_json_string('R2D2')


def test_get_model_list():
    session = base.Session()
    result = get_model_list(session)
    assert 'iAPECO1_1312' in result
    session.close()
    
# Metabolites
def test_get_metabolite_list_for_reaction():
    session = base.Session()
    result = get_metabolite_list_for_reaction('GAPD', session)
    assert 'g3p' in [r['bigg_id'] for r in result]
    assert type(result[0]['stoichiometry']) is Decimal
    assert 'c' in [r['compartment_bigg_id'] for r in result]
    session.close()
    
def test_get_metabolite():
    session = base.Session()
    result = get_metabolite('akg', session)
    assert result['bigg_id'] == 'akg'
    assert result['name'] == '2-Oxoglutarate'
    assert 'c' in [c['bigg_id'] for c in result['compartments_in_models']]
    assert 'iAPECO1_1312' in [c['model_bigg_id'] for c in result['compartments_in_models']]
    assert 'Escherichia coli APEC O1' in [c['organism'] for c in result['compartments_in_models']]
    assert {'link': 'http://www.genome.jp/dbget-bin/www_bget?cpd:C00026', 'id': 'C00026'} \
        in result['database_links']['KEGG']
    session.close()
    

def test_get_model_comp_metabolite(session):
    result = get_model_comp_metabolite('akg', 'c', 'iAPECO1_1312', session)
    assert result['bigg_id'] == 'akg'
    assert result['name'] == '2-Oxoglutarate'
    assert result['compartment_bigg_id'] == 'c'
    assert result['formula'] == 'C5H4O5'
    assert 'AKGDH' in [r['bigg_id'] for r in result['reactions']]
    assert 'iAPECO1_1312' not in [r['bigg_id'] for r in result['other_models_with_metabolite']]
    # make sure models are being filtered
    result = get_model_comp_metabolite('h', 'c', 'iAPECO1_1312', session)
    assert all([r['model_bigg_id'] == 'iAPECO1_1312' for r in result['reactions']])
    

def test_get_metabolites_for_model():
    session = base.Session()
    results = get_metabolites_for_model('iAPECO1_1312', session)
    assert 'akg' in [x['bigg_id'] for x in results]
    assert 'c' in [x['compartment_bigg_id'] for x in results]
    assert 'url' in results[0]
    session.close()

# genes
def test_get_gene_list_for_model():
    session = base.Session()
    results = get_gene_list_for_model('iAPECO1_1312', session)
    assert 'APECO1_706' in [x['bigg_id'] for x in results]
    session.close()

def test_get_gene_list_for_model_reaction(session):
    mr_db = (session
             .query(ModelReaction)
             .join(Model)
             .join(Reaction)
             .filter(Model.bigg_id == 'iAF1260')
             .filter(Reaction.bigg_id == 'ATPM')
             .filter(Reaction.pseudoreaction == True)
             .first())
    results = get_gene_list_for_model_reaction(mr_db.id, session)
    assert len(results) == 0

    mr_db = (session
             .query(ModelReaction)
             .join(Model)
             .join(Reaction)
             .filter(Model.bigg_id == 'iAF1260')
             .filter(Reaction.bigg_id == 'NTP1')
             .filter(Reaction.pseudoreaction == False)
             .first())
    results = get_gene_list_for_model_reaction(mr_db.id, session)
    assert len(results) == 2


def test_get_model_gene(session):
    result = get_model_gene('APECO1_706', 'iAPECO1_1312', session)
    assert result['bigg_id'] == 'APECO1_706'


# database sources
def test_get_database_sources(session):
    assert 'KEGGID' in get_database_sources(session)
    
        
# Escher maps
def test_escher_maps_for_reaction(session):
    maps = get_escher_maps_for_reaction('GAPD', 'iMM904', session)
    assert 'iMM904.Central carbon metabolism' in [x['map_name'] for x in maps]
    assert '669341' in maps[0]['element_id']


def test_escher_maps_for_metabolite(session):
    maps = get_escher_maps_for_metabolite('atp', 'c', 'iMM904', session)
    assert 'iMM904.Central carbon metabolism' == maps[0]['map_name']
    assert '672110' in maps[0]['element_id']
    

def test_json_for_map():
    session = base.Session()
    map_json = json_for_map('iMM904.Central carbon metabolism', session)
    assert isinstance(map_json, unicode)
    assert json.loads(map_json)[0]['homepage'] == 'https://escher.github.io'
    session.close()


# search
def test_search_for_genes(session):
    results = search_for_genes('APECO1_706', session)
    assert results[0]['bigg_id'] == 'APECO1_706'
    assert results[0]['model_bigg_id'] == 'iAPECO1_1312'
    results = search_for_genes('APECO1_706', session,
                               limit_models=['iAPECO1_1312', 'iJO1366'])
    assert results[0]['bigg_id'] == 'APECO1_706'
    results = search_for_genes('APECO1_706', session, limit_models=['iJO1366'])
    assert len(results) == 0
    results = search_for_genes('APECO1_706_6', session)
    assert len(results) == 0
    # test query == ''
    results = search_for_genes('', session)
    assert len(results) == 0


def test_search_for_universal_reactions(session):
    results = search_for_universal_reactions('GAPD', session)
    assert results[0]['bigg_id'] == 'GAPD'
    assert results[0]['model_bigg_id'] == 'universal'
    

def test_search_for_reactions(session):
    time1 = time.time()
    results = search_for_reactions('GAPD', session)
    time2 = time.time()
    print 'search_for_reactions took %0.3f ms' % ((time2 - time1) * 1000.0)

    assert results[0]['bigg_id'] == 'GAPD'
    assert 'iAPECO1_1312' in [x['model_bigg_id'] for x in results]
    results = search_for_reactions('GAPD-', session)
    assert results[0]['bigg_id'] == 'GAPD'
    # test name search
    results = search_for_reactions('Glyceraldehyde-3-phosphate dehydrogenase', session)
    assert 'GAPD' in [x['bigg_id'] for x in results]
    

def test_search_for_universal_metabolites(session):
    results = search_for_universal_metabolites('g3p', session)
    assert results[0]['bigg_id'] == 'g3p'
    assert results[0]['model_bigg_id'] == 'universal'


def test_search_for_metabolites():
    session = base.Session()
    results = search_for_metabolites('g3pd', session)
    assert 'g3p' in [x['bigg_id'] for x in results]
    assert 'iAPECO1_1312' in [x['model_bigg_id'] for x in results]
    # strict
    results = search_for_metabolites('g3p_c', session, strict=True)
    assert 'g3p' in [x['bigg_id'] for x in results]
    assert 'c' in [x['compartment_bigg_id'] for x in results]
    # catch bug where there are a MILLION results:
    assert len(results) <= len(get_model_list(session))
    results = search_for_metabolites('g3p', session, strict=True)
    assert results == []
    session.close()
    
def test_search_for_models():
    session = base.Session()
    results = search_for_models('iAPECO1_1312', session)
    assert results[0]['bigg_id'] == 'iAPECO1_1312'
    assert 'metabolite_count' in results[0]
    assert 'organism' in results[0]
    results = search_for_models('iAPECO1_1312-', session)
    assert results[0]['bigg_id'] == 'iAPECO1_1312'
    # by organism
    results = search_for_models('Escherichia coli', session)
    assert 'iAPECO1_1312' in [x['bigg_id'] for x in results]
    session.close()

def test_search_ids_fast():
    session = base.Session()
    
    time1 = time.time()
    results = search_ids_fast('ga', session)
    time2 = time.time()
    print 'l = 2, search_ids_fast took %0.3f ms' % ((time2 - time1) * 1000.0)
    
    time1 = time.time()
    results = search_ids_fast('gap', session)
    time2 = time.time()
    print 'l = 3, search_ids_fast took %0.3f ms' % ((time2 - time1) * 1000.0)

    time1 = time.time()
    results = search_ids_fast('gapd', session)
    time2 = time.time()
    print 'l = 4, search_ids_fast took %0.3f ms' % ((time2 - time1) * 1000.0)
    assert 'GAPD' in results

    # organism
    results = search_ids_fast('Escherichia coli', session)
    assert 'Escherichia coli APEC O1' in results
    session.close()
