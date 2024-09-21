import sys
import json
import glob
import apache_beam as beam
from apache_beam.io import fileio
from apache_beam.options.pipeline_options import PipelineOptions
from datetime import datetime


class ConvertUHOnlineToNDJson(beam.DoFn):
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

if __name__=='__main__':
    print("[*] Starting...")
    infiles = glob.glob("results/*urlhaus_online")

    with beam.Pipeline() as pipeline:
        print("    [*] transforming data...")
        to_process = (
            pipeline
            | "match files" >> fileio.MatchFiles("results/*urlhaus_online")
            | "read files" >> fileio.ReadMatches()
        )
        converted_file_data = (
            to_process
            | "convert to ndjson" >> beam.ParDo(ConvertUHOnlineToNDJson())
        )
        convert_to_obs_schema = (
           converted_file_data
           | "transform ndjson to obs schema" >> beam.ParDo(TransformObservables())
        )
        print("    [*] writing output files...")
        write_to_disk = (
           convert_to_obs_schema
           | "write to tempdir" >> beam.io.WriteToText("transformed/urlhaus_online")
        )
    print("[.] Done.")
#
