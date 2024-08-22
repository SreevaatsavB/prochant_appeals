import streamlit as st
import pandas as pd
import json
import concurrent.futures
import numpy as np
import os 
from openai import OpenAI
from filetransfer import dump_to_json, read_json_file, delete_directory_contents
from utils import get_denial_mappings, get_clubbed_denials, get_flowchart

os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]

client = OpenAI()

# global df_payor_denial_cn

if "payor_name" not in st.session_state:
    st.session_state["payor_name"] = None

if "club_reasons" not in st.session_state:
    st.session_state["club_reasons"] = False

if "df_payor" not in st.session_state:
    st.session_state["df_payor"] = None

if "denial_reason" not in st.session_state:
    st.session_state["denial_reason"] = None

if "processed_df" not in st.session_state:
    st.session_state["processed_df"] = None

if "denial_code" not in st.session_state:
    st.session_state["denial_code"] = None

if "selected_keys" not in st.session_state:
    print("oopioes")
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


    t2 = t[t['count']==1].reset_index(drop='index')
    t2.columns = ['OriginalInvoiceNumber','count']

    t3 = pd.merge(df_1, t2, on='OriginalInvoiceNumber')

    return t3


def get_denial_code_entries(denial_code, t3, df):

    t4 = t3[t3['DenialCode']==denial_code].reset_index(drop='index')
    t4.columns = ['OriginalInvoiceNumber','final_DenialCode','count']

    # st.write("processed_df")
    # st.write("t4")
    # st.write(t4)

    df3 = pd.merge(df, t4, on='OriginalInvoiceNumber')

    # st.write("df_payor")
    # st.write("df3")
    # st.write(df3)

    df3 = df3[df3['Status']=='Closed    '].reset_index(drop='index')

    return df3



def return_call_note_responses(i, df):

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
                "content": df.loc[i]['CallNotes'] +'''Fetch the various actions that the agent has taken and the reason why the actions are taken along with the issue for the above claim note as a JSON so that I can group similar call notes together - example of an action is that the agent calculated fee schedule, searched in a portal, raised appeal etc.
                Make sure to ensure all the keys mentioned abover are present.'''
            }],
        response_format={ "type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)


def process_call_notes_parallel(df, num_rows, max_threads=10):
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
        # Pass the dataframe to each thread
        futures = [executor.submit(return_call_note_responses, i, df) for i in range(num_rows)]

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

    new_mapping_list = []
    curr_mappings = st.session_state["mappings"][payor_name][medical_code]

    for key in curr_mappings:

        if key in selected_keys:
            new_mapping_list += curr_mappings[key]

    
    st.session_state["mappings"][payor_name][medical_code][new_group_name] = new_mapping_list

    for key in selected_keys:
        
        if key == new_group_name:
            continue
        else:
            del st.session_state["mappings"][payor_name][medical_code][key]


    # new_mapping = []
    # for key in selected_keys:
    #     new_mapping += st.session_state["clubbed_mapping"][key]

    # st.session_state["clubbed_mapping"][new_group_name] = new_mapping

    # for key in selected_keys:
    #     if key == new_group_name:
    #         continue

    #     else:
    #         del st.session_state["clubbed_mapping"][key]
    
    return st.session_state["mappings"][payor_name][medical_code]


def club_codes(codes, new_group_name, payor_name, df_payor, processed_df):

    if len(codes) == 1 and new_group_name == codes[0]:
        return st.session_state["mappings"][payor_name]


    for dcode in codes:
        filename = f'call_notes/call_notes_{payor_name}_{dcode}.json'

        if os.path.exists(filename):
            continue 

        else:
            df_denial_code = get_denial_code_entries(dcode, processed_df, df_payor)
            df_payor_denial = df_denial_code[['CallNotes']].drop_duplicates().dropna().reset_index(drop=True)
            

            num_rows = min(df_payor_denial.shape[0], 300)
            json_actions_parallel = process_call_notes_parallel(df_payor_denial, num_rows, max_threads=100)

            dump_to_json(json_actions_parallel, filename)
            # st.write(f"Processed and saved data to {filename}")

    num_codes = len(codes)

    max_entries = 300//num_codes

    new_code_data = []

    for dcode in codes:
        filename = f'call_notes/call_notes_{payor_name}_{dcode}.json'

        if os.path.exists(filename):
            json_data_code = read_json_file(filename)

            for i in range(min(len(json_data_code), max_entries)):
                new_code_data.append(json_data_code[i])
        

    # st.write("new_code_data len = ", len(new_code_data))
    print("new_code_data len = ", new_code_data)

    new_filename = f'call_notes/call_notes_{payor_name}_{new_group_name}.json'
    dump_to_json(new_code_data, new_filename)


    
    for c in codes:
        if c not in st.session_state["mappings"][payor_name]:
            st.session_state["mappings"][payor_name][c] = {}

    new_mapping = {}
    for c in codes:

        curr_dir = st.session_state["mappings"][payor_name][c]

        new_mapping.update(curr_dir)

    st.session_state["mappings"][payor_name][new_group_name] = new_mapping

    for c in codes:

        if c == new_group_name:
            continue

        else:
            del st.session_state["mappings"][payor_name][c]

    return st.session_state["mappings"][payor_name]


def delete_reasons(medical_code, del_reasons, payor_name):

    for dr in del_reasons:
        if medical_code in st.session_state["mappings"][payor_name] and dr in st.session_state["mappings"][payor_name][medical_code]:
            del st.session_state["mappings"][payor_name][medical_code][dr]

    # for dr in del_reasons:
    #     del st.session_state["clubbed_mapping"][dr]

    return list(st.session_state["mappings"][payor_name][medical_code].keys())

def get_callnote_codes(d_codes, processed_df, df_payor):

    codes_op = []

    for denial_code in d_codes:
        df_denial_code = get_denial_code_entries(denial_code, processed_df, df_payor)
        print(denial_code)
        print(df_denial_code.shape)
        print(  )
        if df_denial_code.shape[0] > 30:
            codes_op.append(denial_code)

    print(codes_op)
    return codes_op 



with st.sidebar:

    with st.container():
        st.write("Click here to get the flowchart from the start")

        if st.button("Ask again"):
            for k in st.session_state:
                del st.session_state[k]


            delete_directory_contents("call_notes")

            st.rerun()



st.markdown('## Denial Management Flowchart Generator')

if st.session_state["payor_name"] is not None:
    idxpn = list(df['PayorName'].unique()).index(st.session_state["payor_name"])

else:
    idxpn = None
payor_name = st.selectbox('Select a Payor Name', df['PayorName'].unique(), index = idxpn)
# st.session_state["payor_name"] = payor_name

if payor_name:  
    payor_name = payor_name.replace('/', '_')


if payor_name not in st.session_state["mappings"]:
    st.session_state["mappings"][payor_name] = {}


if payor_name:

    # st.text("step 1")
    # st.text(st.session_state["payor_name"])


    if st.session_state["df_payor"] is None:


        df_payor = get_payorname_entries(payor_name, df)
        st.session_state["df_payor"] = df_payor

        processed_df = process_data(df_payor)
        st.session_state["processed_df"] = processed_df



        if payor_name != st.session_state["payor_name"]:
            
            all_codes = list(processed_df['DenialCode'].unique())
            denial_code_options = get_callnote_codes(all_codes, processed_df, df_payor)
            # st.text(denial_code_options)

        else:
            denial_code_options = list(st.session_state["mappings"][payor_name].keys())

        st.session_state["payor_name"] = payor_name
        ####

    else:

        if st.session_state["payor_name"] != payor_name:
            df_payor = get_payorname_entries(payor_name, df)
            st.session_state["df_payor"] = df_payor

            processed_df = process_data(df_payor)

            st.session_state["processed_df"] = processed_df
            st.session_state["club_reasons"] = False

            # denial_code_options = list(st.session_state["mappings"][payor_name].keys())
            all_codes = list(processed_df['DenialCode'].unique())
            denial_code_options = get_callnote_codes(all_codes, processed_df, df_payor)

        else:
            denial_code_options = list(st.session_state["mappings"][payor_name].keys())

        df_payor = st.session_state["df_payor"]
        processed_df = st.session_state["processed_df"]
    
    # processed_df.to_csv("temp1.csv")

    ########################################################################################
    # Merging the codes
    
    st.markdown("### Select or Club remark codes")
    st.markdown("#### ** Ensure to give a group name")


    # list(processed_df['DenialCode'].unique())
    for c in denial_code_options:
        if c not in st.session_state["mappings"][payor_name]:
            st.session_state["mappings"][payor_name][c] = {}

        else:
            continue
        
    selected_dcs = st.multiselect('Select remark codes to club together', denial_code_options, key = "66")

    print("selected codes = ", selected_dcs)
    print()

    for k in selected_dcs:
        st.session_state["selected_dcs"].append(k)

    new_group_name = st.session_state["denial_code"]

    if st.session_state["selected_dcs"] != []:

        new_group_name = st.text_input('Enter a name for the new group of codes **',value=None)

        if st.button('Club Selected Remark Codes', key = "1221"):
            if new_group_name:
                updated_mapping = club_codes(selected_dcs, new_group_name, payor_name, df_payor, processed_df)
                st.write(f"Updated remark codes for {selected_dcs}: {new_group_name}")
            else:
                st.warning("Please enter a name for the new group of codes")

        else:
            pass
            # st.warning("Please enter a name for the new group of codes")

                
    
    curr_denial_code = new_group_name

    # st.write(st.session_state["mappings"][payor_name])
    #############################################################################
    

    if curr_denial_code is not None:

        if st.session_state["denial_code"] is None:

            df_denial_code = get_denial_code_entries(curr_denial_code, processed_df, df_payor)
            df_payor_denial_cn = df_denial_code[['CallNotes']].drop_duplicates().dropna().reset_index(drop=True)


            # st.text("No.of entries = " + str(df_payor_denial_cn.shape[0]))
            
            print("No.of callnotes retieved = ", df_payor_denial_cn.shape)

            filename = f'call_notes/call_notes_{payor_name}_{curr_denial_code}.json'

            if os.path.exists(filename):
                json_data = read_json_file(filename)
                st.write(f"Loaded data from {filename}")

            else:
                num_rows = min(df_payor_denial_cn.shape[0], 300)
                json_actions_parallel = process_call_notes_parallel(df_payor_denial_cn, num_rows, max_threads=100)

                dump_to_json(json_actions_parallel, filename)
                # st.write(f"Processed and saved data to {filename}")
                json_data = read_json_file(filename)


            reasons = []
            for i in range(len(json_data)):
                try:
                    reasons.append(json_data[i]['claim_notes'][0]['denial_reason'])
                except:
                    continue


            if st.session_state["mappings"][payor_name][curr_denial_code] != {}:
                clubbed_mapping = st.session_state["mappings"][payor_name][curr_denial_code]

            else:
                denial_mappings = get_denial_mappings(reasons)

                if "denial_mappings" not in st.session_state:
                    st.session_state["denial_mappings"] = denial_mappings


                clubbed_mapping = get_clubbed_denials(denial_mappings)

                if "clubbed_mapping" not in st.session_state:
                    st.session_state["clubbed_mapping"] = clubbed_mapping

                st.session_state["mappings"][payor_name][curr_denial_code] = clubbed_mapping

                st.session_state["denial_code"] = curr_denial_code


            denial_mappings = st.session_state["denial_mappings"]
            clubbed_mapping = st.session_state["clubbed_mapping"]
        

        else:

            print(curr_denial_code, st.session_state["denial_code"])

            if curr_denial_code != st.session_state["denial_code"]:

                df_denial_code = get_denial_code_entries(curr_denial_code, processed_df, df_payor)
                df_payor_denial_cn = df_denial_code[['CallNotes']].drop_duplicates().dropna().reset_index(drop=True)


                print("No.of callnotes retieved = ", df_payor_denial_cn.shape)


                # st.text(df_payor_denial_cn.shape)

                filename = f'call_notes/call_notes_{payor_name}_{curr_denial_code}.json'

                if os.path.exists(filename):
                    json_data = read_json_file(filename)
                    st.write(f"Loaded data from {filename}")

                else:
                    num_rows = min(df_payor_denial_cn.shape[0], 300)
                    json_actions_parallel = process_call_notes_parallel(df_payor_denial_cn, num_rows, max_threads=100)

                    dump_to_json(json_actions_parallel, filename)
                    # st.write(f"Processed and saved data to {filename}")
                    json_data = read_json_file(filename)


                reasons = []
                for i in range(len(json_data)):
                    try:
                        reasons.append(json_data[i]['claim_notes'][0]['denial_reason'])
                    except:
                        continue

                        
                if curr_denial_code == "":
                    pass

                else:
                    if st.session_state["mappings"][payor_name][curr_denial_code] != {}:
                        clubbed_mapping = st.session_state["mappings"][payor_name][curr_denial_code]


                    else:
                        denial_mappings = get_denial_mappings(reasons)

                        if "denial_mappings" not in st.session_state:
                            st.session_state["denial_mappings"] = denial_mappings


                        clubbed_mapping = get_clubbed_denials(denial_mappings)


                        if "clubbed_mapping" not in st.session_state:
                            st.session_state["clubbed_mapping"] = clubbed_mapping

                        st.session_state["mappings"][payor_name][curr_denial_code] = clubbed_mapping

                        st.session_state["denial_code"] = curr_denial_code


            # df_payor_denial_cn
            denial_mappings = st.session_state["denial_mappings"]
            clubbed_mapping = st.session_state["clubbed_mapping"]


        denial_mappings = st.session_state["denial_mappings"]
        clubbed_mapping = st.session_state["clubbed_mapping"]

        # st.text("present mappins")
        # st.text(st.session_state["mappings"][payor_name][curr_denial_code])


        # st.write("clubbed mappings = ", st.session_state["clubbed_mapping"])


        if curr_denial_code is not None:
            denial_code = curr_denial_code

        else:
            denial_code = st.session_state["denial_code"]
            

        if denial_code not in st.session_state["mappings"][payor_name]:
            st.session_state["mappings"][payor_name][denial_code] = {}

    
        # st.session_state["mappings"][payor_name][denial_code] = clubbed_mapping
        # reasons_selected = clubbed_mapping[denial_reason]


        filename = f'call_notes/call_notes_{payor_name}_{denial_code}.json'


        if os.path.exists(filename):
            json_data = read_json_file(filename)

        # st.write(clubbed_mapping)
        # st.write(st.session_state["clubbed_mapping"])

        reasons_to_display = []

        for dr in st.session_state["mappings"][payor_name][denial_code]:

            reasons_selected = st.session_state["mappings"][payor_name][denial_code][dr]

            notes = []

            for i in range(len(json_data)):
                note = json_data[i]
                try:
                    if note['claim_notes'][0]['denial_reason'] in reasons_selected:
                        notes.append(note)
                except:
                    continue
            
            if len(notes) == 0:
                continue

            else:
                reasons_to_display.append(dr)
                print(dr, len(notes))
                
        # st.text("reasons to display")
        # st.text(reasons_to_display)

        new_reason_dict = {}

        for res in reasons_to_display:
            if res not in new_reason_dict:
                new_reason_dict[res] = st.session_state["mappings"][payor_name][denial_code][res]

        st.session_state["mappings"][payor_name][denial_code] = new_reason_dict

        # st.session_state["clubbed_mapping"] = new_reason_dict

        # reasons_to_display
        
        st.markdown("### Clubbing denial reasons")

        selected_keys = st.multiselect('Select denial reasons to club together', list(st.session_state["mappings"][payor_name][denial_code].keys()), key = "1")


        print("1. selected keys = ", selected_keys)
        print()

        for k in selected_keys:
            st.session_state["selected_keys"].append(k)

        print("2. selected keys = ", st.session_state["selected_keys"])
        # print()

        if st.session_state["selected_keys"] != []:

            new_group_name2 = st.text_input('Enter a name for the new group')

            print("CLUBBING")
            print(st.session_state["mappings"][payor_name][denial_code])

            if st.button('Club Selected Denial Reasons', key = "3433"):
                if new_group_name2:
                    updated_mapping = club_denial_reasons(payor_name , denial_code, selected_keys, new_group_name2)
                    print("updated_mapping = ", updated_mapping)
                    st.write(f"Updated denial reasons for {selected_keys}: {new_group_name2}")
                else:
                    st.warning("Please enter a name for the new group")


        # st.text(st.session_state["mappings"][payor_name][denial_code])
        # st.text(st.session_state["clubbed_mapping"])

        st.session_state["club_reasons"] = True

        st.markdown("### Select the denial reasons you want to delete")



        del_reasons = st.multiselect('Select denial reasons to delete', list(st.session_state["mappings"][payor_name][denial_code].keys()), key = "1374")

        # denial_reason_to_delete = st.selectbox('Select a denial reason to delete', list(st.session_state["mappings"][denial_code].keys()))
        
        if st.button('Delete Selected Denial Reason', key = "454"):
            updated_keys = delete_reasons(denial_code, del_reasons, payor_name)
            st.write(f"Deleted denial reasons :- {del_reasons}")

        

        # st.text(st.session_state["clubbed_mapping"].keys())

        st.markdown("### Flowchart ")
        # denial_reason = st.selectbox('Select a Denial Reason', list(st.session_state["mappings"][payor_name][denial_code].keys()), index = None)

        # if st.session_state["denial_reason"] is not None:
        #     idx =  list(st.session_state["clubbed_mapping"].keys()).index(st.session_state["denial_reason"])
        
        # else:
        #     idx = None
        # denial_reason = st.selectbox('Select a Denial Reason', list(st.session_state["clubbed_mapping"].keys()), index = None)
        


#         with st.spinner('Wait for it...'):
#     time.sleep(5)
# st.success("Done!")

        denial_reason = st.selectbox('Select a Denial Reason', list(st.session_state["mappings"][payor_name][denial_code].keys()), index = None)

        st.session_state["denial_reason"] = denial_reason

        print("denial_reason = ", denial_reason)

        if denial_reason:

            with st.spinner('Flowchart being generated .....'):

                flowchart_filename = f'flowcharts/{payor_name}_{denial_code}_{denial_reason}.txt'

                filename = f'call_notes/call_notes_{payor_name}_{denial_code}.json'

                if os.path.exists(filename):
                    json_data = read_json_file(filename)


                reasons_selected = st.session_state["mappings"][payor_name][denial_code][denial_reason]

                notes = []
                for i in range(len(json_data)):
                    note = json_data[i]
                    try:
                        if note['claim_notes'][0]['denial_reason'] in reasons_selected:
                            notes.append(note)
                    except:
                        continue


                print(" ")
                print(notes)
                print(" ")

                if len(notes) == 0:
                    flowchart = "Not enough data for genrating a flowchart"

                else:
                    flowchart = get_flowchart(denial_reason, notes)
                    
                    # Save the flowchart to the text file
                    with open(flowchart_filename, 'w') as file:
                        file.write(flowchart)

                    
                st.success("Flowchat generated!")
                
            
            st.markdown(flowchart)  

            st.markdown('#')
            st.markdown("### Edit the flowchart if needed")
            new_markdown = st.text_area("Edit the flowchart", value=flowchart, height=300)

            with open(flowchart_filename, 'w') as file:
                    file.write(new_markdown)

            st.write(f"Flowchart edited on {flowchart_filename}")

        
            # st.session_state["mappings"][payor_name][denial_code][denial_reason] = new_markdown

# /Users/sreevaatsav/Downloads/temp1 copy/prochant_appeals/filetransfer.py


# 8153 LA CARE (MEDI-CAL)
# CO16, 16
# 