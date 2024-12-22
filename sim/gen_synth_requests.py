import pandas as pd 
import numpy as np
from numpy.random import choice
import random

num_requests = 200



cols = [
    
    {
        'name':'logsources','datatype':'cat', 'req_datatype':'assessment', 'config': 
        {
            'choices':['EDR','SIEM','AV','PROXY'],
            'choices_prob':[0.5,0.2,0.2,0.1]
        },
    },
    {
        'name':'reference_list_needed','datatype':'cat', 'req_datatype':'assessment', 'config': 
        {
            'choices':['YES','NO'],
            'choices_prob':[0.5,0.5]
        },
    },
    {
        'name':'reference_list_exists','datatype':'cat', 'req_datatype':'assessment', 'config': 
        {
            'choices':['YES','NO','NA'],
            'dep_field':'reference_list_needed',
            'valmap':{
                'NO':'NA',
                'YES':{
                    'choices':['YES','NO'],
                    'choices_prob':[0.5,0.5]
                }
            }
        },
    },
    {
        'name':'severity','datatype':'discrete', 'req_datatype':'metrics', 'config': 
        {
            'numrange':[0,5]
        },
    }
]




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
                    row[c['name']] = "*NA"
                else:
                    row[c['name']] = get_choice(c['config']['choices'],c['config']['choices_prob'])
                #
            elif c['datatype']=='discrete':
                row[c['name']] = random.randint(c['config']['numrange'][0], c['config']['numrange'][1])
            #
        #
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
