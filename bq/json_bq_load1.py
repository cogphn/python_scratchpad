import apache_beam as beam
import sys
import json
from apache_beam.io import fileio
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.io.gcp.internal.clients import bigquery
from datetime import datetime



OUTPUT_TABLE = "datasetname.tablename"
SCHEMA = {
"fields":[
    {"name":"observable","type":"STRING","mode":"NULLABLE"},
    {"name":"obstype","type":"STRING","mode":"NULLABLE"},
    {"name":"source","type":"STRING","mode":"NULLABLE"},
    {"name":"importdate","type":"TIMESTAMP","mode":"NULLABLE"},
    {"name":"tags","type":"STRING","mode":"REPEATED"}
]
}


options = PipelineOptions(
  project = "project-name",
  temp_location = "gs://my_tmp_storage99/tmp0",
  region="us-east1",
  job_name = "test-job-00099"
)


class ConvertToNDJson(beam.DoFn):
  def process(self, readablefile):
    with (readablefile.open()) as infile:
      data = json.loads(infile.read())
    ret = []
    for k in data.keys():
      row = data[k][0]
      ret.append(row)
    return ret

class TransformObservables(beam.DoFn):
  def process(self, rdata):
    row = {}
    row["observable"] = rdata["url"]
    row["obstype"] = "url"
    row["source"] = "urlhaus_online"
    row["importdate"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row["tags"] = rdata["tags"]
    return [row]


if __name__ == "__main__":
  with beam.Pipeline(options=options) as pipeline: 
    to_process = (
      pipeline
      | "match files" >> fileio.MatchFiles("gs://my_tmp_storage99/feedsink/*_urlhaus_online")
      | "read files" >> fileio.ReadMatches()
    )
    converted_file_data = (
      to_process
      | "convert to ndjson" >> beam.ParDo(ConvertToNDJson())
    )
    transformed_observables = (
      converted_file_data
      | "transform to desitnation schema" >> beam.ParDo(TransformObservables())
    )
    #print("[*][dbg] writing results to disk...") #dbg
    #write_to_disk = (
    #  transformed_observables
    #  | "write to tmp" >> beam.io.WriteToText("tmp/rando")
      #| "write to gcs tmp storage" >> beam.io.WriteToText("gs://my_tmp_storage99/tmp/tmp_obs_transform")
    #)
    print("[*] writing results to bq...")
    write_to_bq = (
      transformed_observables
      | "write to bq" >> beam.io.WriteToBigQuery(
                           OUTPUT_TABLE,
                           schema=SCHEMA,
                           write_disposition=beam.io.BigQueryDisposition.WRITE_TRUNCATE,
                           create_disposition=beam.io.BigQueryDisposition.CREATE_IF_NEEDED )
    )
  print("[.] done")
