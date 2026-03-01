from google.adk.agents.llm_agent import Agent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from google.adk.agents import LlmAgent
from dotenv import load_dotenv
import os

from pydantic import BaseModel
from typing import Optional, List
from google.adk.agents.sequential_agent import SequentialAgent


load_dotenv()
vt_env = {
    "VT_APIKEY": os.getenv("VT_KEY")
}

default_threat_profile = os.getenv("DEFAULT_THREAT_PROFILE_ID")

secops_customer_id = os.getenv("SECOPS_CUSTOMER_ID")
secops_project_id = os.getenv("SECOPS_PROJECT_ID")
secops_region = os.getenv("SECOPS_REGION")
secops_api_version = os.getenv("SECOPS_API_VERSION")

secops_env = {
    "CHRONICLE_PROJECT_ID": secops_project_id,
    "CHRONICLE_CUSTOMER_ID": secops_customer_id,
    "CHRONICLE_REGION": secops_region
}

gti_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params = StdioServerParameters(
            command='uvx',
            args=[
                "--from",
                "gti-mcp",
                "gti_mcp"
            ],
            env=vt_env
        ),
    ),
)

gso_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params = StdioServerParameters(
            command='uvx',
            args=[
                "--from",
                "google-secops-mcp",
                "secops_mcp"
            ],
            env=secops_env
        ),
    ),
)

class TechniqueListModel(BaseModel):
    techniques: Optional[List[str]] = None
#


## start agent declarations 

ti_agent = Agent(
    model='gemini-2.5-pro',
    name='threat_intelligence_agent',
    description='''
    You are a threat intelligence agent. You answer questions related 
     to cyber threat intelligence. You have access to the google threat 
     intelligence platform (the GTI patform).     
    ''',
    instruction='Answer user questions to the best of your knowledge',
    tools=[gti_toolset]
)

de_agent = Agent(
    name="detection_engineer_agent",
        model="gemini-2.5-pro",
        instruction=f"""
    You are a detecting engineering agent. You are primarily focused on 
    developing and maintining detection content in google SecOps (GSO).
    Rules in google SecOps are written in YARA-L.

    When using the SecOps MCP, use these parameters for EVERY request:
    Customer ID: {os.getenv("SECOPS_CUSTOMER_ID")}
    Region: {os.getenv("SECOPS_REGION", "us")}
    Project ID: {os.getenv("SECOPS_PROJECT_ID")} 
"""  
    ,tools=[gso_toolset]
)

specalized_ti_technique_collector = Agent(
    model='gemini-2.5-pro',
    name='threat_intelligence_technique_collector',
    description='a thret intelligence agent that collects Mitre att&ck techniques and subtechniques for the default threat profile',
    instruction=f'''
    You are a threat intelligence agent. You have access to the google threat 
     intelligence platform (the GTI patform).     
    You are currently only concerned with the threat profile ID
     {default_threat_profile} (this is your default threat profile ID). 
    Your job is to return a list of Mitre ATT&CK TTPs (otherwise known as
    T-codes) that are relevant for this profile ID. You can achive this by 
    first checking all the threat actors associated with your threat profile,
     then checking al the malware assoicated with your threat profile. Once
      you have this information, create a list of all applicable Mitre ATT&CK
       techniques. Ensure duplicates are removed from the list. Also ensure 
    that only Mitre ATT&CK techniques or subtechniques are added to the list.
     Mitre ATT&CK techniques and subtechniques start with T and are followed
      by a series of numbers, sometimes with a decimal place indicating the 
    code is a sub-technique.
    ''',
    tools=[gti_toolset],
    output_schema=TechniqueListModel
)

specalized_de_coverage_checker = Agent(
    model='gemini-2.5-pro',
    name='detection_enginnering_coverage_checker',
    instruction='''
    You are a detection enginnering agent that currently has access to a 
    connected Google SecOps (GSO) instance. You will receive a list of 
    Mitre att&ck techniques from threat intelligece. For each of those 
    techniques and subtechniques, check them against the existing enabled 
    detection rules. Create a new list of Mitre Att&ck techniques and 
    subtechniques which do not have associated detection rules in Google 
     SecOps. Return this list to the user.
    ''',
    description=f''' helpful detection engineering agent that checks 
    for detection coverage
    ''',
    tools=[gso_toolset]
)


default_root_agent = LlmAgent(
    model='gemini-2.5-pro',
    name='root_agent',
    description='''
    helpful security consultant sidekick
    ''',
    instruction='''
    answer questions to the best of your ability. For questions related
     to threat actors, threat profiles or anything to do with threat 
     intelligence, transfer to threat_intelligence_agent.
    For questions related to detection engineering, including questions 
    related to Google SecOps, data feeds, detection rules, and alerts, 
    transfer to detection_engineer_agent.
    ''',
    sub_agents=[ti_agent, de_agent]
)

threat_informed_coverage_checker = SequentialAgent(
    name="ti_coverage_checker",
    sub_agents=[specalized_ti_technique_collector, specalized_de_coverage_checker],
    description="a sequential workflow that looks for detections based on a techniques associated with your threat profile"
)

root_agent = threat_informed_coverage_checker
