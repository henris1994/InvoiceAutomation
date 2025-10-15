import requests
from dotenv import load_dotenv
import os
load_dotenv()

def sql_executor(sql_query: str):
    url = "http://10.10.30.183/api/v1/sqltest" # local IP
    headers = {
        "content-type": "application/json",
        "X-API-Key": os.getenv('sql_client_api_key')
    }
    payload = {
        "sql_query": sql_query
    }

    response = requests.post(url, headers=headers, json=payload)
    try:
        data = response.json()
        return data
    except ValueError:
        return {"ERROR": response.text}

# TO TEST:
# python -m test-sql
if __name__ == "__main__":
    res = sql_executor(sql_query="WITH MainQuery AS (SELECT clntste.clntste_id as SiteId, clntste_stre_nmbr as StoreNo, clntste.clntste_nme as SiteName, wrkordr.wrkordr_id as WorkOrderId, wrkordr.wrkordr_po as PONo, wrkordr.wrkordr_nme as Description, srvcectgry.srvcectgry_id as ServiceCategoryId, wrkordr.wrkordr_type as WorkType, case when right(wrkordr_entrd_by, 1) = '2' OR right(wrkordr_entrd_by, 1) = '3' then reverse(substring(reverse(wrkordr_entrd_by), 2, 25)) else wrkordr_entrd_by end as EnteredBy, wrkordr_dte_opnd + '   ' + LTRIM(RIGHT(CONVERT(VARCHAR(20), cast(wrkordr_tme_opnd as datetime), 100), 7)) + ' (' + left(DATENAME(weekday,wrkordr_dte_opnd),3) + ')' as Created, (select max(wrkordrtchncn_dte_schdld + ' (' + left(DATENAME(weekday,wrkordrtchncn_dte_schdld),3) + ')') from wrkordrtchncn where wrkordrtchncn.wrkordr_rn = wrkordr.wrkordr_rn) as Scheduled, CASE WHEN wrkordr_escltn_stts IN ('Parts Received','Pending') THEN 'Parts Ordered' ELSE wrkordr_escltn_stts END as Status, (SELECT COUNT(wrkordreqpmnt_rn) from wrkordreqpmnt where wrkordreqpmnt.wrkordr_rn = wrkordr.wrkordr_rn) as Equipment, CASE WHEN wrkordr.srvcerqst_wblg_rn <> 0 THEN CONVERT(char(10),wblg_id) ELSE '' END as ServiceRequestNo from wrkordr join clntste on wrkordr.clntste_rn = clntste.clntste_rn join wbprfle on clntste.wbprfle_rn = wbprfle.wbprfle_rn join srvcectgry on wrkordr.srvcectgry_rn = srvcectgry.srvcectgry_rn join wblg on wrkordr.srvcerqst_wblg_rn = wblg.wblg_rn join rmte_wbusrclntste on rmte_wbusrclntste.clntste_rn = clntste.clntste_rn join scrty on wrkordr.scrty_rn = scrty.scrty_rn where rmte_wbusrclntste.wbusr_id = 'dhill' and (wrkordr_stts_ctgry = 'Open') and wrkordr.wrkordr_id >= '700000') SELECT SiteId, StoreNo, SiteName, WorkOrderId, PONo, Description, ServiceCategoryId, WorkType, EnteredBy, Created, Scheduled, Status, Equipment, ServiceRequestNo, EnteredBy FROM MainQuery ORDER BY Created DESC, WorkOrderId")
    print(res)