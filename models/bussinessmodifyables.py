#DETERMINE TAX AUTHORITY ID BY GL_ENTITY OR JOB IDD 
tax_mock=[]
tax_mock = {
    '01a99': 'nassau',
    '02a99': 'nassau',
    '03a99': 'nassau',
    '06a99': 'florida',
    '07a99': 'nassau',
    '11a99':'maryland',
    '12a99':'philadelphia',
    '14a99':'florida',
    '15a99':'massachusetts'
}

jobidtoglentity=[]
#DETERMINE GL ENTITY BY JOB ID 
#GET THE FIRST TWO LETTERS NOT THREE
jobidtoglentity = {
    'RE': '01a99',
    'AL':'02a99',
    'DA': '03a99',
    'SC': '04a99',
    'FL':'06a99',
    'SF':'14a99',
    'DC': '11a99',
    'PE': '12a99',
    'PL': '07a99',
    'BO':'15a99',
    'NC': '13a99',
}

glaccount=[]
#DETERMINE GL account BY glentity #all lowercase
glaccount = {
    '01a99': '2401',
    '02a99': '2401',
    '03a99': '2401',
    '06a99': '2411',
    '07a99': '2401',
    '11a99':'2407',
    '12a99':'2404',
    '14a99':'2411',
    '15a99':'2409'
}