import streamlit as st
import pandas as pd
import json
import concurrent.futures
import numpy as np
import os 
from openai import OpenAI
from filetransfer import dump_to_json, read_json_file
from utils import get_denial_mappings, get_clubbed_denials, get_flowchart

os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]

client = OpenAI()

global df_payor_denial_cn

if "payor_name" not in st.session_state:
    st.session_state["payor_name"] = None

if "club_reasons" not in st.session_state:
    st.session_state["club_reasons"] = False

if "df_payor" not in st.session_state:
    st.session_state["df_payor"] = None

if "processed_df" not in st.session_state:
    st.session_state["processed_df"] = None

if "denial_code" not in st.session_state:
    st.session_state["denial_code"] = None

if "selected_keys" not in st.session_state:
    st.session_state["selected_keys"] = []

if "selected_dcs" not in st.session_state:
    st.session_state["selected_dcs"] = []


# Load the CSV data
df = pd.read_csv('call_notes_all.csv')

if "mappings" not in st.session_state:
    st.session_state["mappings"] = {}

# Functions to process data
def get_payorname_entries(payor_name, df3):
    return df3[df3['PayorName']==payor_name].reset_index(drop='index')


def process_data(df_1):
    df_1 = df_1[['OriginalInvoiceNumber','DenialCode']]
    df_1 = df_1.drop_duplicates()
    df_1 = df_1[~(df_1['DenialCode'].isna())]

    t = df_1['OriginalInvoiceNumber'].value_counts().reset_index()
    t.columns = ["index", "count"]
    # print()
    # print(t.columns)
    # print()

    t2 = t[t['count']==1].reset_index(drop='index')
    t2.columns = ['OriginalInvoiceNumber','count']

    t3 = pd.merge(df_1, t2, on='OriginalInvoiceNumber')

    return t3


def get_denial_code_entries(denial_code, t3, df):

    t4 = t3[t3['DenialCode']==denial_code].reset_index(drop='index')
    t4.columns = ['OriginalInvoiceNumber','final_DenialCode','count']

    frequency = df['OriginalInvoiceNumber'].value_counts().reset_index()
    frequency.columns = ['OriginalInvoiceNumber','freq']
    df3 = pd.merge(df, t4, on='OriginalInvoiceNumber')
    df3 = df3[df3['Status']=='Closed    '].reset_index(drop='index')

    return df3


def return_call_note_responses(i):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages= [
            {
                "role": "system",
                "content": '''you are extremely good at identifying actions, reasons and details from call notes. You help the AR agents who work on denied claims.
                For example, for the following text - Invoice:1004209DOS:8/11/2023Carrier name: 8153 LA CARE (MEDICAL)HCPCS:T4523Denial reason: PaidAction needed to resolve:cashpostNotes:As per the review in payspan EOB found the claim was paid on 09/05/2023 with the amount of $47.52 with the check#946000564977 with the bulk amount $98 012.15.As per the paid calculation (72*0.48*1.38*1*1.1025=52.581312) =52.58.Balance is $5.06.Since the balance is less than $6.00 but it was not posted in caretend.Hence posting he payment and adjusting the balance.Claim#23229E036694 your response will be:
        {
        "claim_notes": [
            {
            "invoice": "1004209",
            "DOS": "8/11/2023",
            "carrier_name": "8153 LA CARE (MEDICAL)",
            "HCPCS": "T4523",
            "denial_reason": "Paid",
            "actions": [
                {
                "action": "Review in payspan EOB",
                "reason": "To check the payment status",
                "details": "EOB found the claim was paid on 09/05/2023 with the amount of $47.52 with the check#946000564977 with the bulk amount $98,012.15."
                },
                {
                "action": "Calculate paid amount",
                "reason": "To verify the payment calculation",
                "details": "As per the paid calculation (72*0.48*1.38*1*1.1025=52.581312) =52.58. Balance is $5.06."
                },
                {
                "action": "Post payment and adjust balance",
                "reason": "Balance is less than $6.00 but it was not posted in caretend",
                "details": "Hence posting the payment and adjusting the balance."
                }
            ],
            "issue": "Claim was paid but not posted in caretend due to balance less than $6.00.",
            "claim_number": "23229E036694"
            }
        ]
        }
        '''
            },
            {
                "role": "user",
                "content": df_payor_denial_cn.loc[i]['CallNotes']+'''Fetch the various actions that the agent has taken and the reason why the actions are taken along with the issue for the above claim note as a JSON so that I can group similar call notes together - example of an action is that the agent calculated fee schedule, searched in a portal, raised appeal etc.
                Make sure to ensure all the keys mentioned abover are present.'''
            }],
        response_format={ "type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

def process_call_notes_parallel(num_rows, max_threads=10):
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = [executor.submit(return_call_note_responses, i) for i in range(num_rows)]

        json_actions = []
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                json_actions.append(result)
            except Exception as e:
                print(f"Error processing call note: {e}")

    return json_actions



# Clubbing and deleting denial reasons functions
def club_denial_reasons(payor_name, medical_code, selected_keys, new_group_name):

    filename = f'call_notes/call_notes_{payor_name}_{medical_code}.json'

    if os.path.exists(filename):
        json_data_code = read_json_file(filename)

    new_json = []

    for dic in json_data_code:

        try:
            print("yoooooo")
            denial_reason = dic["claim_notes"][0]["denial_reason"]

            if denial_reason in selected_keys:
                dic["claim_notes"][0]["denial_reason"] = new_group_name

        except:
            continue

        new_json.append(dic)

    # new_json = {new_json}
    dump_to_json(new_json, filename)
    st.write(f"Clubbed the reasons and saved data to {filename}")


    combined_flowchart = "\n".join(st.session_state["mappings"][medical_code][key] for key in selected_keys)

    st.session_state["mappings"][medical_code][new_group_name] = combined_flowchart
    
    for key in selected_keys:
        del st.session_state["mappings"][medical_code][key]
    
    return st.session_state["mappings"][medical_code]



def club_codes(codes, new_group_name, payor_name, df_payor, processed_df):

    for dcode in codes:
        filename = f'call_notes/call_notes_{payor_name}_{dcode}.json'

        if os.path.exists(filename):
            continue 

        else:
            df_denial_code = get_denial_code_entries(dcode, processed_df, df_payor)
            df_payor_denial_cn = df_denial_code[['CallNotes']].drop_duplicates().dropna().reset_index(drop=True)

            num_rows = min(df_payor_denial_cn.shape[0], 300)
            json_actions_parallel = process_call_notes_parallel(num_rows, max_threads=100)

            dump_to_json(json_actions_parallel, filename)
            st.write(f"Processed and saved data to {filename}")

    num_codes = len(codes)

    max_entries = 300//num_codes

    new_code_data = []

    for dcode in codes:
        filename = f'call_notes/call_notes_{payor_name}_{dcode}.json'

        if os.path.exists(filename):
            json_data_code = read_json_file(filename)

            for i in range(min(len(json_data_code), max_entries)):
                new_code_data.append(json_data_code[i])
        
    
    new_filename = f'call_notes/call_notes_{payor_name}_{new_group_name}.json'
    dump_to_json(new_code_data, new_filename)


    if new_group_name not in st.session_state["mappings"]:
        st.session_state["mappings"][new_group_name] = {}

    else:
        raise("The given group name already exists")
    

    for c in codes:
        if c not in st.session_state["mappings"]:
            st.session_state["mappings"][c] = {}

    new_mapping = {}
    for c in codes:
        new_mapping.update(st.session_state["mappings"][c])

    st.session_state["mappings"][new_group_name] = new_mapping

    for c in codes:
        del st.session_state["mappings"][c]

    return st.session_state["mappings"]




def update_medical_codes(medical_code, denial_reason_to_delete):
    if medical_code in st.session_state["mappings"] and denial_reason_to_delete in st.session_state["mappings"][medical_code]:
        del st.session_state["mappings"][medical_code][denial_reason_to_delete]
    return list(st.session_state["mappings"][medical_code].keys())


def delete_reasons(medical_code, del_reasons):

    for dr in del_reasons:
        if medical_code in st.session_state["mappings"] and dr in st.session_state["mappings"][medical_code]:
            del st.session_state["mappings"][medical_code][dr]

    return list(st.session_state["mappings"][medical_code].keys())


def delete_codes(del_codes):

    for code in del_codes:
        if code in st.session_state["mappings"]:
            del st.session_state["mappings"][code]

    return list(st.session_state["mappings"].keys())





st.markdown('## Denial Management Flowchart Generator')


payor_name = st.selectbox('Select a Payor Name', df['PayorName'].unique())
# st.session_state["payor_name"] = payor_name

if f"payor_dict_{payor_name}" not in st.session_state:
    st.session_state[f"payor_dict_{payor_name}"] = {}


if payor_name:

    if st.session_state["df_payor"] is None:

        st.session_state["payor_name"] = payor_name

        df_payor = get_payorname_entries(payor_name, df)
        st.session_state["df_payor"] = df_payor
        processed_df = process_data(df_payor)
        st.session_state["processed_df"] = processed_df

    else:

        if st.session_state["payor_name"] != payor_name:
            df_payor = get_payorname_entries(payor_name, df)
            st.session_state["df_payor"] = df_payor

            processed_df = process_data(df_payor)

            st.session_state["processed_df"] = processed_df
            st.session_state["club_reasons"] = False

        df_payor = st.session_state["df_payor"]
        processed_df = st.session_state["processed_df"]


    ########################################################################################
    # Merging the codes
    st.markdown("##")
    st.markdown("### Clubbing denial codes")


    # list(processed_df['DenialCode'].unique())
    for c in list(processed_df['DenialCode'].unique()):
        if c not in st.session_state["mappings"]:

            st.session_state["mappings"][c] = {}
            st.session_state[f"payor_dict_{payor_name}"][c] = {}

        else:
            continue

    selected_dcs = st.multiselect('Select denial codes to club together', processed_df['DenialCode'].unique(), key = "66")


    print("selected codes = ", selected_dcs)
    print()

    for k in selected_dcs:
        st.session_state["selected_dcs"].append(k)

     
    if st.session_state["selected_dcs"] is not None:

        new_group_name = st.text_input('Enter a name for the new group of codes')

        if st.button('Club Selected Denial Codes', key = "1221"):
            if new_group_name:
                updated_mapping = club_codes(selected_dcs, new_group_name, payor_name, df_payor, processed_df)
                st.write(f"Updated denial codes for {selected_dcs}: {new_group_name}")
            else:
                st.warning("Please enter a name for the new group of codes")
                

    st.markdown("##")
    st.markdown("### Deleting denial codes")


    del_codes = st.multiselect('Select denial codes to be deleted', list(st.session_state["mappings"].keys()), key = "1554")

    # denial_reason_to_delete = st.selectbox('Select a denial reason to delete', list(st.session_state["mappings"][denial_code].keys()))
    
    if st.button('Delete Selected Denial Codes', key = "4504"):
        updated_keys = delete_codes(del_codes)
        st.write(f"Deleted denial codes :- {del_codes}")




    #############################################################################
    
    st.markdown("##")
    st.markdown("### Get flowchart for the denial reasons")
    # Denial code selection
    curr_denial_code = st.selectbox('Select a Denial Code', list(st.session_state["mappings"].keys()))


    if curr_denial_code not in st.session_state[f"payor_dict_{payor_name}"]:
        st.session_state[f"payor_dict_{payor_name}"][curr_denial_code] = {}
        

    if st.session_state["denial_code"] is None:

        
        df_denial_code = get_denial_code_entries(curr_denial_code, processed_df, df_payor)
        df_payor_denial_cn = df_denial_code[['CallNotes']].drop_duplicates().dropna().reset_index(drop=True)

        filename = f'call_notes/call_notes_{payor_name}_{curr_denial_code}.json'

        if os.path.exists(filename):
            json_data = read_json_file(filename)
            st.write(f"Loaded data from {filename}")

        else:
            num_rows = min(df_payor_denial_cn.shape[0], 300)
            json_actions_parallel = process_call_notes_parallel(num_rows, max_threads=100)

            dump_to_json(json_actions_parallel, filename)
            st.write(f"Processed and saved data to {filename}")
            json_data = read_json_file(filename)


        reasons = []
        for i in range(len(json_data)):
            try:
                reasons.append(json_data[i]['claim_notes'][0]['denial_reason'])
            except:
                continue

        keys_json = get_denial_mappings(reasons)

        if "keys_json" not in st.session_state:
            st.session_state["keys_json"] = keys_json
            st.session_state[f"payor_dict_{payor_name}"][curr_denial_code]["keys_json"] = keys_json


        new_json_mapping = get_clubbed_denials(keys_json)

        if "new_json_mapping" not in st.session_state:
            st.session_state["new_json_mapping"] = new_json_mapping
            st.session_state[f"payor_dict_{payor_name}"][curr_denial_code]["new_json_mapping"] = new_json_mapping


        st.session_state["denial_code"] = curr_denial_code

        # keys_json = st.session_state["keys_json"]
        # new_json_mapping = st.session_state["new_json_mapping"]
    

    else:

        print(curr_denial_code, st.session_state["denial_code"])

        if curr_denial_code != st.session_state["denial_code"]:

            df_denial_code = get_denial_code_entries(curr_denial_code, processed_df, df_payor)
            df_payor_denial_cn = df_denial_code[['CallNotes']].drop_duplicates().dropna().reset_index(drop=True)

            filename = f'call_notes/call_notes_{payor_name}_{curr_denial_code}.json'

            if os.path.exists(filename):
                json_data = read_json_file(filename)
                st.write(f"Loaded data from {filename}")

            else:
                num_rows = min(df_payor_denial_cn.shape[0], 300)
                json_actions_parallel = process_call_notes_parallel(num_rows, max_threads=100)

                dump_to_json(json_actions_parallel, filename)
                st.write(f"Processed and saved data to {filename}")
                json_data = read_json_file(filename)


            reasons = []
            for i in range(len(json_data)):
                try:
                    reasons.append(json_data[i]['claim_notes'][0]['denial_reason'])
                except:
                    continue

            keys_json = get_denial_mappings(reasons)

            if "keys_json" not in st.session_state:
                st.session_state["keys_json"] = keys_json

            new_json_mapping = get_clubbed_denials(keys_json)

            # if "new_json_mapping" not in st.session_state:
            st.session_state["new_json_mapping"] = new_json_mapping
            st.session_state[f"payor_dict_{payor_name}"][curr_denial_code]["new_json_mapping"] = new_json_mapping
            

            st.session_state["keys_json"] = keys_json
            st.session_state[f"payor_dict_{payor_name}"][curr_denial_code]["keys_json"] = keys_json

            st.session_state["denial_code"] = curr_denial_code


        # keys_json = st.session_state["keys_json"]
        # new_json_mapping = st.session_state["new_json_mapping"]

        keys_json = st.session_state[f"payor_dict_{payor_name}"][curr_denial_code]["keys_json"]
        new_json_mapping = st.session_state[f"payor_dict_{payor_name}"][curr_denial_code]["new_json_mapping"]



    keys_to_consider = new_json_mapping.keys()

    denial_code = curr_denial_code

    if denial_code not in st.session_state["mappings"]:
        st.session_state["mappings"][denial_code] = {}

    for k in keys_to_consider:
        st.session_state["mappings"][denial_code][k] = ""
 
    st.session_state["mappings"][denial_code] = new_json_mapping

    st.markdown("##")
    st.markdown("### Clubbing denial reasons")

    selected_keys = st.multiselect('Select denial reasons to club together', list(st.session_state["mappings"][denial_code].keys()), key = "1")


    print("selected keys = ", selected_keys)
    print()

    for k in selected_keys:
        st.session_state["selected_keys"].append(k)

     
    if st.session_state["selected_keys"] is not None:

        new_group_name = st.text_input('Enter a name for the new group')

        print(st.session_state["mappings"][denial_code])

        if st.button('Club Selected Denial Reasons', key = "3433"):
            if new_group_name:
                updated_mapping = club_denial_reasons(payor_name , denial_code, selected_keys, new_group_name)
                st.write(f"Updated denial reasons for {denial_code}: {updated_mapping}")
            else:
                st.warning("Please enter a name for the new group.")

    
    st.session_state["club_reasons"] = True



    st.markdown("##")
    st.markdown("### Select the denial reasons you want to delete")

    del_reasons = st.multiselect('Select denial reasons to delete', list(st.session_state["mappings"][denial_code].keys()), key = "1374")

    # denial_reason_to_delete = st.selectbox('Select a denial reason to delete', list(st.session_state["mappings"][denial_code].keys()))
    
    if st.button('Delete Selected Denial Reason', key = "454"):
        updated_keys = delete_reasons(denial_code, del_reasons)
        st.write(f"Updated denial reasons for {denial_code}: {updated_keys}")

    st.markdown("##")

    st.markdown("### Flowchart ")
    denial_reason = st.selectbox('Select a Denial Reason', list(new_json_mapping.keys()), index=None)

    if denial_reason:

        flowchart_filename = f'flowcharts/{payor_name}_{denial_code}_{denial_reason}.txt'

        if os.path.exists(flowchart_filename):
            # If the file exists, read the flowchart from the file
            st.write(f"Loaded data from {flowchart_filename}")
            with open(flowchart_filename, 'r') as file:
                flowchart = file.read()

        else:

            filename = f'call_notes/call_notes_{payor_name}_{denial_code}.json'

            if os.path.exists(filename):
                json_data = read_json_file(filename)

            # If the file doesn't exist, generate the flowchart and save it
            # notes = [note for note in json_data if note['claim_notes'][0]['denial_reason'] == denial_reason]

            notes = []
            for i in range(len(json_data)):
                note = json_data[i]
                try:
                    if note['claim_notes'][0]['denial_reason'] == denial_reason:
                        notes.append(note)
                except:
                    continue

            if len(notes) == 0:
                flowchart = "Not enough data for genrating a flowchart"

            else:
                flowchart = get_flowchart(denial_reason, notes)
                
                # Save the flowchart to the text file
                with open(flowchart_filename, 'w') as file:
                    file.write(flowchart)

                st.write(f"Flowchart written to {flowchart_filename}")
            
        st.markdown(flowchart)  

        st.markdown('#')
        st.markdown("### Edit the flowchart if needed")
        new_markdown = st.text_area("Edit the flowchart", value=flowchart, height=300)

        with open(flowchart_filename, 'w') as file:
                file.write(new_markdown)

        st.write(f"Flowchart edited on {flowchart_filename}")

        st.session_state["mappings"][denial_code][denial_reason] = new_markdown




# 8153 LA CARE (MEDI-CAL)
# CO16, 16
# 