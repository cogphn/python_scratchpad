import pandas as pd 
import numpy as np
from numpy.random import choice
import random
import json



num_requests = 500
mitredata = None
with open("mitredata.json") as infile:
    mitredata = json.loads(infile.read())


with open("colcfg.json") as infile:
    cols = json.loads(infile.read())




def get_choice(choices:list, choices_prob:list):
    return str(choice(choices, 1, choices_prob)[0])
#

def setval_choices(choices_dict:dict):
    return get_choice(choices_dict['choices'], choices_dict['choices_prob'])
#


if __name__ == "__main__":
    print("[*] Starting...")

    i=0
    data = []
    dep_fields = []
    while i < num_requests:
        row = {}
        for c in cols:
            row[c['name']] = ''            
            if c['datatype']=='cat':                
                choices = c['config']['choices']
                if 'dep_field' in c['config']:
                    dfield = {'fieldname':c['name'], 'config':c['config'] }

                    if dfield not in dep_fields:
                        dep_fields.append({'fieldname':c['name'], 'config':c['config'] })
                    row[c['name']] = "NA"
                else:
                    row[c['name']] = get_choice(c['config']['choices'],c['config']['choices_prob'])
                #
            elif c['datatype']=='discrete':
                row[c['name']] = random.randint(c['config']['numrange'][0], c['config']['numrange'][1])
            #
        #
        randtechnique = mitredata[random.randint(0,len(mitredata))]
        row['tactic'] = randtechnique['tactic']
        row['technique'] = randtechnique['technique']
        i +=1
        data.append(row)

    df = pd.DataFrame(data)
    for dep in dep_fields:
        valmap = dep['config']['valmap']
        ref_field = dep['config']['dep_field']
        for k in valmap.keys():
            src_field_val = k
            if type(valmap[k]).__name__ == 'dict':
                choicesdict = valmap[k]                
                for i,r in df.iterrows():
                    if r[ref_field]==src_field_val:
                        newval = setval_choices(choicesdict)
                        df.iloc[i, df.columns.get_loc(dep['fieldname'])] = newval
                    #
                #
            else:
                df.loc[df[ref_field]==src_field_val,dep['fieldname']] = '*'+valmap[k]
            #
    
    df.to_csv("output.csv", index=False)
    

    print("[.] done")
