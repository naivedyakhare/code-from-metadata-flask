from flask import Flask, request, jsonify, render_template
import openai

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('home.html')

@app.route('/generate', methods=['POST'])
def generate():
    # To create chat history
    global messages
    
    messages = []
    role_system = {"role": "system", "content": "You are a SAS programmer assitant. You will create SAS Code for clinical trials metadata specification following SDTM Guidelines."}
    reference_prompt = '''
        I have given you Reference Metadata and Reference Code below. Use it to learn how to generate SAS code.

        # Reference Metadata
        Variable_Name, Variable_Label, Type, Derivation, example
        STUDYID, Study Identifier, Char, demo.study_id, 101
        DOMAIN, Domain Abbreviation, Char, dm, dm
        USUBJID, Unique Subject Identifier, Char, demo.study_id + '-' + demo.site_id + '-'  + demo.subjid, 101-11-0011
        SUBJID, Subject Identifier for the Study, Char, demo.subjid, 0011
        RFSTDTC, Subject Reference Start Date/Time, Char, first expo.exdtc, 2020-12-13
        RFENDTC, Subject Reference End Date/Time, Char, last expo.exdtc, 2020-05-14
        RFXSTDTC, First Date/Time of Exposure, Char, first expo.exdtc, 2020-12-13
        RFXENDTC, Last Date/Time of Exposure, Char, last expo.exdtc, 2020-05-14
        RFICDTC, Informed Consent, Char, desp.cons_dt, 2020-12-01
        REPENDTC, Date/Time of End of Participation, Char, last date of ( expo.exdtc, desp.ds_dt ), 2020-05-24
        DTHDTC, Date/Time of Death, Char, desp.death_dt, 2020-05-24
        DTHFL, Subject Death Flag, Char, Y' if desp.death_dt is not missing, Y
        SITEID, Study Site Identifier, Char, demo.site_id, 11
        BRTHDTC, Date / Time of Birth, Char, demo.brith_dt, 1990-02-22
        AGE, Age, Num,  year of  desp.cons_dt - year of demo.birth_dt , 30
        AGEU, Age Units, Char, YEARS, YEARS
        SEX, Sex, Char, demo.sex, M
        RACE, Race, Char, demo.race, WHITE
        ARMCD, Planned Arm Code, Char, rand.trt_cd, C
        ARM, Description of Planned Arm, Char, rand.trt, CONTROL
        ACTARMCD, Actual Arm Code, Char, rand.trt_cd, C
        ACTARM, Description of Actual Arm, Char, rand.trt, CONTROL
        ARMNRSN, Reason Arm and/or Actual Arm is Null, Char, rand.trt_reas, UNPLANNED TREATMENT
        ACTARMUD, Description of Unplanned Actual Arm, Char, rand.trt_reas2, MISTAKE FROM SITE
        COUNTRY, Country, Char, USA, USA

        # reference code:
        ** Assign studyid, domain, subjid, siteid, usubjid, birthdtc, ageu, sex, race, country from rawdata demo;
        data _dm;
        set demo;

        studyid = study_id;
        domain = 'dm';
        subjid = subjid;
        siteid = site_id;
        usubjid = study_id + '-' + site_id + '-' + subjid;
        birthdtc = birth_dt;

        ageu = 'YEARS'
        sex = sex;
        race = race;

        country = 'USA';

        keep studyid domain subjid siteid usubjid birthdtc ageu sex race country;

        run;

        ** find the first and last drug taken by patients from rawdata expo;
        proc sql;
            create table expo_first_last as
            select subjid,
                min(ex_dt) as rfstdtc,
                max(ex_dt) as rfendtc
        
            from expo
        where ex_dt is not null
            group by subjid;
        quit;

        ** Obtain rficdtc dthdtc dthfl from rawdata desp;
        data _ds;
        set desp;

        rficdtc = cons_dt;
        dthdtc = death_dt;

        if dthdtc is not missing then dthfl = 'Y';

        keep rficdtc dthdtc dthfl term_dt;

        run;

        ** Obtain arm armcd actarm actarmcd armnrsn actarmud from rawdata rand;
        data _rand;
        set rand;

        arm = trt
        if trt = 'Control' then armcd = 'C';
        else if trt = 'Study Drug' then armcd = 'S';

        actarm = arm ;
        actarmcd = armcd ;

        armnrsn = trt_reas;
        actarmud = trt_reas;

        keep arm armcd actarm actarmcd armnrsn actarmud ;
        run;

        ** Merge all the data together ;
        data dm;
        merge _dm(in=a) expo_first_last _ds _rand;
        by subjid;

        if a;

        rfxstdtc = rfstdtc;
        rfxendtc = rfendtc;

        rependtc = max(rfendtc, term_dt );

        rficdt = input(rficdtc, yymmdd10.);
            birthdt = input(birthdtc, yymmdd10.);
            age = (rficdt - birthdt) / 365.25;

        drop rficdt birthdt term_dt ;
        run;

        I will give you query or metadata in the next prompt. You will need to create SAS code based on the query or metadata I give you next.
    '''
    messages.append(role_system)
    messages.append({"role": "user", "content": reference_prompt})
    
    data = request.get_json()
    api_key = data['apiKey']
    prompt = data['prompt']
    # Generating prompt that will be an input
    prompt = f'''
{prompt}

You have been given the metadata. Create a code in the SAS based on the given metadata.
Give raw code without any suffix or prefix or ``` symbols. Raw code that can be straight up executed.
        '''
    
    messages.append({"role": "user", "content": prompt})
    
    client = openai.OpenAI(api_key=api_key)
    
    try:
        return jsonify({'generatedCode': output_from_response(call_openai(client, messages))})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# HELPING FUNCTIONS

def output_from_response(response):
    output = ""
    stream_chunk = list([*response])
    for chunk in stream_chunk:
        if chunk.choices != []:
            if chunk.choices[0].delta.content is not None:
                output += chunk.choices[0].delta.content

    return output


def call_openai(client, messages):
    return client.chat.completions.create(
                model='gpt-4-turbo',  # or use another engine suitable for code generation
                messages=messages,
                stream=True,
                stream_options={"include_usage": True}
    )

if __name__ == '__main__':
    app.run(debug=True)