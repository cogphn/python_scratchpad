import json
import pandas as pd
import sqlite3
from sqlalchemy import create_engine


def main():
    # TODO: obviously rewrite 

    conn = create_engine("sqlite:///mitredata.db")

    infile = "data/enterprise-attack-18.1.json"
    print("  [*] reading input file...")
    with open(infile) as inf:
        data = json.loads(inf.read())
    
    mitre_objects = data['objects']

    tactic_data = [x for x in mitre_objects if x['type']=='x-mitre-tactic']
    technique_data = [x for x in mitre_objects if x['type']=='attack-pattern' and x['x_mitre_deprecated']==False]
    coa_data = [x for x in mitre_objects if x['type']=='course-of-action' and x['x_mitre_deprecated']==False and x['revoked']==False]
    obj_relationships = [x for x in mitre_objects if x['type']=='relationship' and x['x_mitre_deprecated']==False]
    analytic_data = [x for x in mitre_objects if x['type']=='x-mitre-analytic']
    detection_data = [x for x in mitre_objects if x['type']=='x-mitre-detection-strategy' and x['x_mitre_deprecated']==False]

    print("  [*] processing tactics...")
    tactics = [
        {
            'id': x['id'],
            'created': x['created'],
            'modified': x['modified'],
            'name': x['name'],
            'description': x['description'],
            'external_id': x['external_references'][0]['external_id']
        } for x in tactic_data
    ]

    tactics_df = pd.DataFrame(tactics)
    tactics_df.to_sql("tactics", con=conn, if_exists='replace')

    print("  [*] processing techniques...")
    techniques = [
        {
            'id': x['id'],
            'created': x['created'],
            'modified': x['modified'],
            'name': x['name'],
            'description': x['description'],
            'external_id': x['external_references'][0]['external_id'],
            'kill_chain_phases': x['kill_chain_phases'],
            'platforms': x['x_mitre_platforms']
        } for x in technique_data
    ]

    techniques_df = pd.DataFrame(techniques)
    tech_kill_chains = techniques_df[['id','external_id','kill_chain_phases']].explode(['kill_chain_phases']).copy()
    tech_kill_chains['kill_chain_phases'] = tech_kill_chains['kill_chain_phases'].str['phase_name']
    techniques_df = techniques_df.drop('kill_chain_phases', axis=1).copy()
    techniques_df = techniques_df.drop('platforms', axis=1).copy()
    
    
    techniques_df.to_sql("techniques", con=conn, if_exists='replace')
    tech_kill_chains.to_sql("technique_tactics", con=conn, if_exists='replace')

    print("  [*] processing courses of action...")
    courses_of_action = [
        {
            'id': x['id'],
            'created': x['created'],
            'modified': x['modified'],
            'name': x['name'],
            'description': x['description'],
            'external_id': x['external_references'][0]['external_id'],
        } for x in coa_data
    ]

    courses_of_action_df = pd.DataFrame(courses_of_action)

    print("  [*] processing relationships...")
    relationships = [
        {
            'id': x['id'],
            'created': x['created'],
            'modified': x['modified'],
            #'description': x['description'],
            'source_ref': x['source_ref'],
            'target_ref': x['target_ref'],
        } for x in obj_relationships
    ]

    relationships_df = pd.DataFrame(relationships)
    relationships_df.to_sql("relationships", con=conn, if_exists='replace')


    print("  [*] processing analytics...")
    analytics = [
        {
            'id': x['id'],
            'created': x['created'],
            'modified': x['modified'],
            'name': x['name'],
            'description': x['description'],
            'external_id': x['external_references'][0]['external_id'],
            #'platforms': x['x_mitre_platforms'],
        } for x in analytic_data
    ]

    analytics_df = pd.DataFrame(analytics)
    analytics_df.to_sql("analytics", con=conn, if_exists='replace')
    
    print("  [*] processing detections...")
    detections = [
        {
            'id': x['id'],
            'created': x['created'],
            'modified': x['modified'],
            'name': x['name'],
            'external_id': x['external_references'][0]['external_id'],
            'x_mitre_analytic_refs': x['x_mitre_analytic_refs']
        } for x in detection_data
    ]

    detections_df = pd.DataFrame(detections)

    detection_analytics = detections_df[['id','name','external_id','x_mitre_analytic_refs']].explode(['x_mitre_analytic_refs']).copy()
    detections_df = detections_df.drop('x_mitre_analytic_refs', axis=1)
    detections_df.to_sql("detections", con=conn, if_exists='replace')
    detection_analytics.to_sql("detection_analytics", con=conn, if_exists='replace')
#



if __name__ == "__main__":
    print("[*] starting...")

    main()
