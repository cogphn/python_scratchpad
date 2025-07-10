#import mesa
from mesa import Agent, Model , time
import random, string
import numpy as np
import uuid
#from datetime import datetime 




'''
TODO:
 - initial access: phishing/ valid creds. If phishing, attempt to phish workstations, becomes infected based on defined probability 
 - attacker objectives.
    1. lateral movement -> move laterally until you find a domain controller / file server / backup server
        - if you find a domain controller, you immediately know where all other server types are and can execute on the next objective
    2. data theft. Once you find a file server, execute data theft  
    3. ransomware. Once you finish exfiltrating data (might take a couple ticks depending on the size of data)
    2.5. destroy backups maybe. if you find a backup server, see how you can break backup jobs 
 - network artifacts for c2, data exfil - find a way to record the network artifact on the workstation agent 
 - responders! - they might detect adversary activity 
 - multiple threat actors 
 - CREDS
'''


'''
def getAgentData():
    names = [n.unique_id for n in model.schedule.agents]
    states = [a.state for a in model.schedule.agents]
    networks = [n.domain for n in model.schedule.agents]
    roles = [n.role for n in model.schedule.agents]
'''

class AdversaryAgent(Agent):
    def __init__(self, unique_id, model):
        super().__init__(unique_id,model)
        self.name = unique_id
        self.stealth = np.random.rand(1)
        self.access_goal = "move laterally" # could be one of: "get access", "move laterally", "exfiltrate data", "deploy ransomware"
        self.rw_goal = "find data"
        self.found_dc = False
        self.found_data = False
        self.found_priv_creds = False
        self.compromised_computers = None
        self.infected_computers = None
        self.got_data = False
        #self.owned = [n.unique_id for n in model.schedule.agents]

    def step(self) -> None:
        
        self.compromised_computers =  [n.unique_id for n in self.model.schedule.agents if type(n).__name__ == "ComputerAgent" and n.state =="compromised"]
        self.infected_computers =  [n.unique_id for n in self.model.schedule.agents if type(n).__name__ == "ComputerAgent" and n.state =="infected"]

        #access goals 
        if len(self.compromised_computers) > 0:
            self.access_goal="move laterally" # traverse environment
        elif len(self.compromised_computers) == 0 and len(self.infected_computers) >0:
            self.access_goal="compromise system" # 
        elif (len(self.compromised_computers) + len(self.infected_computers)) == 0:
            self.access_goal="gain access" # aka 'enter environment'
        #

        for cc in self.compromised_computers:
            if "DS-" in cc.unique_id:
                self.found_data = True
            #


        # rw goals  ## execute objectives 
        if self.found_data and self.goal =="move laterally":
            self.rw_goal = "data theft"
        elif self.found_dc and self.got_data:
            self.rw_goal = "deploy ransomware"
        else:
            self.rw_goal = "find data"
        #

        if self.access_goal == "gain access":
            
            rando = np.random.rand(1)
            
            # see if you can find an exposed server 
            exposed_server_list = [n for n in self.model.schedule.agents if type(n).__name__ == "ComputerAgent" and n.role == "Member Server" and n.pub_exposed]
            if len(exposed_server_list) > 0:
                # exposed server found!
                srv = self.random.choice([n for n in self.model.schedule.agents if type(n).__name__ == "ComputerAgent" and n.role == "Member Server" and n.pub_exposed])
                if rando > 0.9:
                    srv.state = "compromised"
            else: 
                # no exposed servers :-( - try phishing maybe
                # get a random workstation
                ws = self.random.choice([n for n in self.model.schedule.agents if type(n).__name__ == "ComputerAgent" and n.role == "Workstation"])
                if rando > 0.94:
                    ws.state = state = "compromised"
                #
            #
        elif self.access_goal == "move laterally":
            None
        #
     
    #


class ComputerAgent(Agent):
    def __init__(self, unique_id, model):
        super().__init__(unique_id,model)
        self.state = "not compromised"
        self.has_priv_creds = False # this shouldn't change 
        self.domain = None
        self.has_sensitive_data = False
        self.role = "Member Server"
        self.pub_exposed = False
        self.attacker_evidence = [] # list of attacker tools or other evidence that was dropped by the attacker 

        if str(self.unique_id).startswith("DC-"):
            self.role = "Domain Controller"
        elif str(self.unique_id).startswith("PC-"):
            self.role = "Workstation"
        else:
            # member server 
            rando = np.random.rand(1)
            if rando > 0.9:
                self.pub_exposed = True
                #todo :add some logic for the type of exposure -> web/ rdp
            #
        
    def step(self) -> None:
        
        next_computer = self.random.choice(self.model.schedule.agents) #pick a random computer agent
        if self.state == "compromised" and next_computer.domain == self.domain and self.has_priv_creds and next_computer.state !="encrypted":
            next_computer.state = "compromised"
        #
        if self.role=="Domain Controller" and self.state == "compromised":
            agents = self.model.schedule.agents
            for a in agents:
                if a.domain == self.domain:
                    a.state = "encrypted"
                #
            #
        #
        if self.state=="infected":
            rando = np.random.rand(1)
            if rando > 0.8 and self.role =="Member Server":
                self.state = "compromised"
            if rando > 0.5 and self.role == "Workstation":
                self.state == "compromised"
        #
    #

class RedModel(Model):

    simid = None

    def __init__(self, num_computers, num_TAs=1):
        self.num_agents = num_computers + num_TAs
        self.num_computers = num_computers
        self.ticks = 0
        self.schedule = time.RandomActivation(self)

        computer_name_prefixes = ['PC-','SRV-','FS-','DS-','DC-']
        computer_name_prefix_probabilities = [0.4, 0.2, 0.2, 0.1, 0.1] # figure out how to parameterize

        computer_states = ["not compromised","compromised","infected"]
        computer_state_probabilities = [0.9,0.05,0.05]

        networks = ["CORPNET.LAN","dev.local","DMZ"]
        netcon_probs = [0.7,0.1,0.2]
        
        simid = str(uuid.uuid4())
        for i in range(self.num_computers):
            #generate computer name 
            suffix = ''.join(random.choice(string.ascii_letters) for _ in range (5)) ##
            prefix = np.random.choice(computer_name_prefixes,size=None,p=computer_name_prefix_probabilities)
            cname = f"{prefix}{suffix}{i}"

            c = ComputerAgent(cname, self)
            c.state = np.random.choice(computer_states,size=None,p=computer_state_probabilities)
            
            c.has_priv_creds = np.random.choice([True,False],None,[0.2,0.8])

            if c.role == "Domain Controller":
                c.has_priv_creds = True     # DC will always have creds 
                c.state = "not compromised" # for the sake of the model, assume a DC can't be the first compromised system 
            #

            c.domain = np.random.choice(networks,None,netcon_probs)

            self.schedule.add(c)
        #

        ## 
        compromised_computers =  [n for n in self.schedule.agents if type(n).__name__ == "ComputerAgent" and n.state =="compromised"]
        infected_computers =  [n for n in self.schedule.agents if type(n).__name__ == "ComputerAgent" and n.state =="infected"]
        attacker = AdversaryAgent("FIN333",self)
        attacker.compromised_computers = compromised_computers
        attacker.infected_computers = infected_computers

        self.schedule.add(attacker)

        
        
    #

    def step(self):
        self.schedule.step()
        self.ticks += 1
        print(self.schedule.time)


