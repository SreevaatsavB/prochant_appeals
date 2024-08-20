import os 
from openai import OpenAI
import json
import streamlit as st


os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
client = OpenAI()


def get_denial_mappings(reasons):

    prompt = '''Here are a set of codes as a list: ''' + str(reasons) + "\n\n" '''Generate a mapping of unique reasons to the content in list as a mapping strictly as a JSON. Be extremely aggressive in mapping so that we have very few unique keys'''

    response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages= [
        {
            "role": "user",
            "content": prompt
        }],
    response_format={ "type": "json_object"}
    )

    json_mapping = json.loads(response.choices[0].message.content)

    return json_mapping


def get_clubbed_denials(keys_json):

    prompt = '''Here are a set of mapping of denials and the different ways in which they can be mentioned.
    Please club the denials that are highly related and share the exhaustive set of reasons in the below JSON
    ''' + str(keys_json) +''' A sample structure is:
    {'Paid': ['Paid'],
    'Denied - Past TFL': ['Denied - Past TFL'],
    'Duplicate': ['Duplicate', 'Duplicate Denial', 'CO-18 Duplicate Denial'],
    'No Authorization': ['No Authorization']
    }

    For example, group together terms like 'Past TFL' and 'Timely Filing Expired,' which refer to the same or closely related concepts.
    Be aggressive in mapping so that we have as few unique keys as possible, ensuring that all related terms are consolidated

    '''

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages= [
            {
                "role": "user",
                "content": prompt
            }],
        response_format={ "type": "json_object"}
        )
    

    new_json_mapping = json.loads(response.choices[0].message.content)
    return new_json_mapping


def get_flowchart(k, notes):

    prompt = "Here are a set of actions (jsons) taken by agents to resolve a denied claim with the following denial reason: " +  k + " " +  str(notes) + '''\nYou are a virtual agent helping new joinees in AR team to address claim denials.
    You are a virtual agent helping new joinees in AR team to address claim denials.
        Please give a decision tree (flowchart of the process) so that new agents can refer to how other agents have handled
        such denials.
        Please ensure to cover as many scenarios as possible while being as simple as possible for new agents.
        Make sure to specify the software the agent has to refer/ work on wherever applicable.

    Output format should look like the below (example of UPN missing scenario):
    The workflow should be structured in a step-by-step format, clearly outlining the actions to be taken at each step. Here are thr example format:
    The claim was denied due to missing UPN.
    Reviewed the claim in Payspan; the reason for denial was missing UPN.
    Checked the medical portal, but UPN was not found.
    Reviewed the payment report; no UPN information found.
    Called customer service to verify if UPN is required.
    Customer service confirmed UPN is required.
    Need to request UPN information from the patient or provider.
    If UPN is obtained, update the claim and resubmit.
    If UPN is not obtained, raise an appeal with the necessary documents.

    Just give the flowchart in words'''

    response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages= [{"role": "user",
                        "content":prompt}]
            # response_format={ "type": "json_object"}
            )


    flowchart = response.choices[0].message.content

    return flowchart