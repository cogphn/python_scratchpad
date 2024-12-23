import pandas as pd
import json 
import tqdm

with open("./ref_datasets/enterprise-attack-16.1.json") as enterprise_infile:
    enterprise_matrix = json.load(enterprise_infile)
#


if __name__ == "__main__":
    print("[*] starting...")
    techniques = [x for x in enterprise_matrix['objects'] if x['type'] == 'attack-pattern']

    list_techniques = []
    list_tactics = []

    data = []
    for t in tqdm.tqdm(techniques):
        tactic = t['external_references'][0]['url'].replace("https://attack.mitre.org/techniques/","").split("/")[0]
        technique = t['external_references'][0]['url'].replace("https://attack.mitre.org/techniques/","").replace("/",".")
        tactic_names = [x['phase_name'] for x in t['kill_chain_phases']]
        r = {
            "tactic":tactic,
            "technique":technique,
            "tactic_names":tactic_names,
            "name":t['name']
        }        
        data.append(r)
    #

    df = pd.DataFrame(data)    
    with open("mitredata.json","w") as outfile:
        outfile.write(df.to_json(orient="records", index=False))
    
    print("[.] Done")
#
