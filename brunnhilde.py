#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Brunnhilde v1.0.0
---

A Siegfried-based digital archives reporting tool

For information on usage and dependencies, see:
github.com/timothyryanwalsh/brunnhilde

Python 2.7

The MIT License (MIT)
Copyright (c) 2016 Tim Walsh
http://bitarchivist.net

"""

import argparse
import csv
import datetime
import errno
from itertools import islice
import os
import re
import shutil
import sqlite3
import subprocess
import sys

def run_siegfried(source_dir):
	'''Run siegfried on directory'''
	# run siegfried against specified directory
	print("\nRunning Siegfried against %s. This may take a few minutes." % source_dir)
	global sf_command
	sf_command = "sf -csv -hash md5 '%s' > %s" % (source_dir, sf_file)
	if args.scanarchives == True:
		sf_command = sf_command.replace('sf -csv', 'sf -z -csv')
	if args.throttle == True:
		sf_command = sf_command.replace('-csv -hash', '-csv -throttle 10ms -hash')
	subprocess.call(sf_command, shell=True)
	print("\nCharacterization complete. Processing results.")
	return sf_command
	
def run_clamav(source_dir):
    '''Run ClamAV on directory'''
    # run virus check on specified directory
    timestamp = str(datetime.datetime.now())
    print("\nRunning virus check on %s. This may take a few minutes." % source_dir)
    virus_log = 'viruscheck-log.txt'
    clamav_command = "clamscan -i -r '%s' | tee %s" % (source_dir, virus_log)
    subprocess.call(clamav_command, shell=True)
    # add timestamp
    target = open(virus_log, 'a')
    target.write("Date scanned: %s" % timestamp)
    target.close()
    # compare number of files scanned to inventory of source_dir
    inventory = []
    for root, directories, filenames in os.walk(source_dir):
        for filename in filenames:
            inventory.append(os.path.join(root, filename))
    with open(virus_log) as f:
        for line in f:
            if "Scanned files: " in line:
                scnd = line.split()
                diff = len(inventory) - int(scnd[2])
                if diff >= 1:
                    msg = ("\nThe virus scan missed %s file(s) in %s" % (diff, source_dir))
                    q = " Do you want to keep processing (y/n)?"
                    target = open(virus_log, 'a')
                    target.write("%s" % msg)
                    target.close()
                    raw_answer = raw_input(msg + q)
                    answer = str.lower(raw_answer)
                    if answer == "n":
                        sys.exit()
                else:
                    msg = ("\nThe virus scan missed %s files in %s" % (diff, source_dir))
                    target = open(virus_log, 'a')
                    target.write("%s" % msg)
                    target.close()
                    print(msg)
    # check log for infected files
    if "Infected files: 0" not in open(virus_log).read():
        raw_answer = raw_input("Infected file(s) found. Do you want to keep processing (y/n)?")
        answer = str.lower(raw_answer)
        if answer == "n":
            sys.exit()
    else:
        print("No infections found in %s." % source_dir)

def run_bulkext(source_dir):
	'''Run bulk extractor on directory'''
	# run bulk extractor against specified directory if option is chosen
	bulkext_log = os.path.join(log_dir, 'bulkext-log.txt')
	print("\nRunning Bulk Extractor on %s. This may take a few minutes." % source_dir)
	try:
		os.makedirs(bulkext_dir)
	except OSError as exception:
		if exception.errno != errno.EEXIST:
			raise
	bulkext_command = "bulk_extractor -S ssn_mode=2 -o %s -R '%s' | tee %s" % (bulkext_dir, source_dir, bulkext_log)
	subprocess.call(bulkext_command, shell=True)

def import_csv():
	'''Import csv file into sqlite db'''
	with open(sf_file, 'rb') as f:
		reader = csv.reader(f)
		header = True
		for row in reader:
			if header:
				header = False # gather column names from first row of csv
				sql = "DROP TABLE IF EXISTS siegfried"
				cursor.execute(sql)
				sql = "CREATE TABLE siegfried (filename text, filesize text, modified text, errors text, md5 text, namespace text, id text, format text, version text, mime text, basis text, warning text)"
				cursor.execute(sql)
				insertsql = "INSERT INTO siegfried VALUES (%s)" % (", ".join([ "?" for column in row ]))
				rowlen = len(row)
			else:
				# skip lines that don't have right number of columns
				if len(row) == rowlen:
					cursor.execute(insertsql, row)
		conn.commit()

def get_stats(source_dir, scan_started):
	'''Get aggregate statistics and write to html report'''
	
	# get stats from sqlite db
	cursor.execute("SELECT COUNT(*) from siegfried;") # total files
	num_files = cursor.fetchone()[0]

	cursor.execute("SELECT COUNT(DISTINCT md5) from siegfried WHERE filesize<>'0';") # distinct files
	distinct_files = cursor.fetchone()[0]

	cursor.execute("SELECT COUNT(*) from siegfried where filesize='0';") # empty files
	empty_files = cursor.fetchone()[0]

	cursor.execute("SELECT COUNT(md5) FROM siegfried t1 WHERE EXISTS (SELECT 1 from siegfried t2 WHERE t2.md5 = t1.md5 AND t1.filename != t2.filename) AND filesize<>'0'") # duplicates
	all_dupes = cursor.fetchone()[0]

	cursor.execute("SELECT COUNT(DISTINCT md5) FROM siegfried t1 WHERE EXISTS (SELECT 1 from siegfried t2 WHERE t2.md5 = t1.md5 AND t1.filename != t2.filename) AND filesize<>'0'") # distinct duplicates
	distinct_dupes = cursor.fetchone()[0]

	duplicate_copies = int(all_dupes) - int(distinct_dupes) # number of duplicate copies of unique files
	duplicate_copies = str(duplicate_copies)

	cursor.execute("SELECT COUNT(*) FROM siegfried WHERE id='UNKNOWN';") # unidentified files
	unidentified_files = cursor.fetchone()[0]

	year_sql = "SELECT DISTINCT SUBSTR(modified, 1, 4) as 'year' FROM siegfried;" # min and max year
	year_path = os.path.join(csv_dir, 'uniqueyears.csv')
	with open(year_path, 'wb') as year_report:
		w = csv.writer(year_report)
		for row in cursor.execute(year_sql):
			w.writerow(row)
	with open(year_path, 'rb') as year_report:
		r = csv.reader(year_report)
		years = []
		for row in r:
			years.append(row[0])
		begin_date = min(years, key=float)
		end_date = max(years, key=float)
	os.remove(year_path) # delete temporary "uniqueyear" file from csv reports directory

	datemodified_sql = "SELECT DISTINCT modified FROM siegfried;" # min and max full modified date
	datemodified_path = os.path.join(csv_dir, 'datemodified.csv')
	with open(datemodified_path, 'wb') as date_report:
		w = csv.writer(date_report)
		for row in cursor.execute(datemodified_sql):
			w.writerow(row)
	with open(datemodified_path, 'rb') as date_report:
		r = csv.reader(date_report)
		dates = []
		for row in r:
			dates.append(row[0])
		earliest_date = min(dates)
		latest_date = max(dates)

	cursor.execute("SELECT COUNT(DISTINCT format) as formats from siegfried WHERE format <> '';") # number of identfied file formats
	num_formats = cursor.fetchone()[0]

	cursor.execute("SELECT COUNT(*) FROM siegfried WHERE errors <> '';") # number of siegfried errors
	num_errors = cursor.fetchone()[0]

	cursor.execute("SELECT COUNT(*) FROM siegfried WHERE warning <> '';") # number of siegfried warnings
	num_warnings = cursor.fetchone()[0]

	# get size from du and format
	size = subprocess.check_output(['du', '-sh', source_dir])
	size = size.replace('%s' % source_dir, '')
	size = size.replace('K', ' KB')
	size = size.replace('M', ' MB')
	size = size.replace('G', ' GB')

	# write html
	html.write('<!DOCTYPE html>')
	html.write('\n<html lang="en">')
	html.write('\n<head>')
	html.write('\n<title>Brunnhilde report for: %s</title>' % basename)
	html.write('\n<meta http-equiv="Content-Type" content="text/html; charset=utf-8">')
	html.write('\n<link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/css/bootstrap.min.css" integrity="sha384-BVYiiSIFeK1dGmJRAkycuHAHRg32OmUcww7on3RYdg4Va+PmSTsz/K68vbdEjh4u" crossorigin="anonymous">')
	html.write('\n</head>')
	html.write('\n<body max>')
	html.write('\n<h1>Brunnhilde HTML report</h1>')
	html.write('\n<h3>Input source (directory or disk image)</h3>')
	html.write('\n<p>%s</p>' % os.path.abspath(args.source))
	html.write('\n<h3>Accession/Identifier</h3>')
	html.write('\n<p>%s</p>' % basename)
	html.write('\n<h2>Provenance information</h2>')
	html.write('\n<h3>Brunnhilde version</h3>')
	html.write('\n<p>%s</p>' % brunnhilde_version)
	html.write('\n<h3>Siegfried version</h3>')
	html.write('\n<p>%s</p>' % siegfried_version)
	html.write('\n<h3>Siegfried command</h3>')
	html.write('\n<p>%s</p>' % sf_command)
	html.write('\n<h3>Time of scan</h3>')
	html.write('\n<p>%s</p>' % scan_started)
	html.write('\n<h2>Aggregate stats</h2>')
	html.write('\n<h3>Overview</h3>')
	html.write('\n<p>Total files: %s</p>' % num_files)
	html.write('\n<p>Total size: %s</p>' % size)
	html.write('\n<p>Years (last modified): %s - %s</p>' % (begin_date, end_date))
	html.write('\n<p>Earliest date: %s</p>' % earliest_date)
	html.write('\n<p>Latest date: %s</p>' % latest_date)
	html.write('\n<h3>File contents*</h3>')
	html.write('\n<p>Distinct files: %s</p>' % distinct_files)
	html.write('\n<p>Distinct files that have duplicates: %s</p>' % distinct_dupes)
	html.write('\n<p>Duplicate copies of distinct files: %s</p>' % duplicate_copies)
	html.write('\n<p>Empty files: %s</p>' % empty_files)
	html.write('\n<p>*<em>Calculated by md5 hash. Empty files are not counted in first three categories. Total files = distinct files + duplicate copies + empty files.</em></p>')
	html.write('\n<h3>Format identification</h3>')
	html.write('\n<p>Identified file formats: %s</p>' % num_formats)
	html.write('\n<p>Unidentified files: %s</p>' % unidentified_files)
	html.write('\n<p>Siegfried warnings: %s</p>' % num_warnings)
	html.write('\n<h3>Errors</h3>')
	html.write('\n<p>Siegfried errors: %s</p>' % num_errors)
	html.write('\n<h2>Detailed reports</h2>')
	html.write('\n<p><a href="#File formats">File formats</a></p>')
	html.write('\n<p><a href="#File formats and versions">File formats and versions</a></p>')
	html.write('\n<p><a href="#MIME types">MIME types</a></p>')
	html.write('\n<p><a href="#Last modified dates by year">Last modified dates by year</a></p>')
	html.write('\n<p><a href="#Unidentified">Unidentified</a></p>')
	html.write('\n<p><a href="#Warnings">Warnings</a></p>')
	html.write('\n<p><a href="#Errors">Errors</a></p>')
	html.write('\n<p><a href="#Duplicates">Duplicates</a></p>')
	if args.bulkextractor == True:
		html.write('\n<p><a href="#Personally Identifiable Information (PII)">Personally Identifiable Information (PII)</a></p>')

def generate_reports():
	'''Run sql queries on db to generate reports, write to csv and html'''
	full_header = ['Filename', 'Filesize', 'Date modified', 'Errors', 'Checksum', 
				'Namespace', 'ID', 'Format', 'Format Version', 'MIME type', 
				'Basis for ID', 'Warning']

	# sorted format list report
	sql = "SELECT format, id, COUNT(*) as 'num' FROM siegfried GROUP BY format ORDER BY num DESC"
	path = os.path.join(csv_dir, 'formats.csv')
	format_header = ['Format', 'ID', 'Count']
	sqlite_to_csv(sql, path, format_header)
	write_html('File formats', path, ',')

	# sorted format and version list report
	sql = "SELECT format, id, version, COUNT(*) as 'num' FROM siegfried GROUP BY format, version ORDER BY num DESC"
	path = os.path.join(csv_dir, 'formatVersions.csv')
	version_header = ['Format', 'ID', 'Version', 'Count']
	sqlite_to_csv(sql, path, version_header)
	write_html('File formats and versions', path, ',')

	# sorted mimetype list report
	sql = "SELECT mime, COUNT(*) as 'num' FROM siegfried GROUP BY mime ORDER BY num DESC"
	path = os.path.join(csv_dir, 'mimetypes.csv')
	mime_header = ['MIME type', 'Count']
	sqlite_to_csv(sql, path, mime_header)
	write_html('MIME types', path, ',')

	# dates report
	sql = "SELECT SUBSTR(modified, 1, 4) as 'year', COUNT(*) as 'num' FROM siegfried GROUP BY year ORDER BY num DESC"
	path = os.path.join(csv_dir, 'years.csv')
	year_header = ['Year Last Modified', 'Count']
	sqlite_to_csv(sql, path, year_header)
	write_html('Last modified dates by year', path, ',')

	# unidentified files report
	sql = "SELECT * FROM siegfried WHERE id='UNKNOWN';"
	path = os.path.join(csv_dir, 'unidentified.csv')
	sqlite_to_csv(sql, path, full_header)
	write_html('Unidentified', path, ',')

	# warnings report
	sql = "SELECT * FROM siegfried WHERE warning <> '';"
	path = os.path.join(csv_dir, 'warnings.csv')
	sqlite_to_csv(sql, path, full_header)
	write_html('Warnings', path, ',')

	# errors report
	sql = "SELECT * FROM siegfried WHERE errors <> '';"
	path = os.path.join(csv_dir, 'errors.csv')
	sqlite_to_csv(sql, path, full_header)
	write_html('Errors', path, ',')

	# duplicates report
	sql = "SELECT * FROM siegfried t1 WHERE EXISTS (SELECT 1 from siegfried t2 WHERE t2.md5 = t1.md5 AND t1.filename != t2.filename) AND filesize<>'0' ORDER BY md5;"
	path = os.path.join(csv_dir, 'duplicates.csv')
	sqlite_to_csv(sql, path, full_header)
	write_html('Duplicates', path, ',')

def sqlite_to_csv(sql, path, header):
	'''Write sql query result to csv'''
	with open(path, 'wb') as report:
		w = csv.writer(report)
		w.writerow(header)
		for row in cursor.execute(sql):
			w.writerow(row)

def write_html(header, path, file_delimiter):
	'''Write csv file to html table'''
	with open(path, 'rb') as in_file:
		# count lines and then return to start of file
		numline = len(in_file.readlines())
		in_file.seek(0)

		#open csv reader
		r = csv.reader(in_file, delimiter="%s" % file_delimiter)

		# write header
		html.write('\n<a name="%s"></a>' % header)
		html.write('\n<h3>%s</h3>' % header)
		if header == 'Duplicates':
			html.write('\n<p><em>Duplicates are grouped by md5 hash.</em></p>')
		elif header == 'Personally Identifiable Information (PII)':
			html.write('\n<p><em>Potential PII in source, as identified by bulk_extractor.</em></p>')
		
		# if writing PII, handle separately
		if header == 'Personally Identifiable Information (PII)':
			if numline > 5: # aka more rows than just header
				html.write('\n<table class="table table-striped table-bordered table-condensed">')
				#write header
				html.write('\n<tr>')
				html.write('\n<td>File</td>')
				html.write('\n<td>Value Found</td>')
				html.write('\n<td>Context</td>')
				# write data
				for row in islice(r, 4, None): # skip header lines
					html.write('\n</tr>')
					for row in r:
						# write data
						html.write('\n<tr>')
						for column in row:
							html.write('\n<td>' + column + '</td>')
						html.write('\n</tr>')
					html.write('\n</table>')
			else:
				html.write('\nNone found.')

		# otherwise write as normal
		else:
			if numline > 1: #aka more rows than just header
				html.write('\n<table class="table table-striped table-bordered table-condensed">')
				# generate table
				for row in r:
					# write data
					html.write('\n<tr>')
					for column in row:
						html.write('\n<td>' + column + '</td>')
					html.write('\n</tr>')
				html.write('\n</table>')
			else:
				html.write('\nNone found.')
		
		# write link to top
		html.write('\n<p>(<a href="#top">Return to top</a>)</p>')

def close_html():
	'''Write html closing tags'''
	html.write('\n</body>')
	html.write('\n</html>')

def make_tree(source_dir):
	'''Call tree on source directory and save output to tree.txt'''
	# create tree report
	tree_command = "tree -tDhR '%s' > %s" % (source_dir, os.path.join(report_dir, 'tree.txt'))
	subprocess.call(tree_command, shell=True)

def process_content(source_dir):
	'''Run through main processing flow on specified directory'''
	scan_started = str(datetime.datetime.now()) # get time
	run_siegfried(source_dir) # run siegfried
	import_csv() # load csv into sqlite db
	get_stats(source_dir, scan_started) # get aggregate stats and write to html file
	generate_reports() # run sql queries, print to html and csv
	close_html() # close HTML file tags
	make_tree(source_dir) # create tree.txt


""" 
MAIN FLOW 
"""

# system info
brunnhilde_version = 'v1.0.0'
siegfried_version = subprocess.check_output(["sf", "-version"])

# parse arguments
parser = argparse.ArgumentParser()
parser.add_argument("-b", "--bulkextractor", help="Run Bulk Extractor on source", action="store_true")
parser.add_argument("-d", "--diskimage", help="Use disk image instead of dir as input", action="store_true")
parser.add_argument("--hfs", help="Use for raw disk images of HFS disks", action="store_true")
parser.add_argument("-n", "--noclam", help="Skip ClamScan Virus Check", action="store_true")
parser.add_argument("-r", "--removefiles", help="Delete 'carved_files' directory when done (disk image input only)", action="store_true")
parser.add_argument("-t", "--throttle", help="Pause for 1s between Siegfried scans", action="store_true")
parser.add_argument("-v", "--version", help="Display Brunnhilde version", action="version", version="Brunnhilde %s" % brunnhilde_version)
parser.add_argument("-z", "--scanarchives", help="Decompress and scan zip, tar, gzip, warc, arc with Siegfried", action="store_true")
parser.add_argument("source", help="Path to source directory or disk image")
parser.add_argument("basename", help="Accession number or identifier, used as basename for outputs")
args = parser.parse_args()

# global variables
current_dir = os.getcwd()
basename = args.basename
report_dir = os.path.join(current_dir, '%s' % basename)
csv_dir = os.path.join(report_dir, 'csv_reports')
log_dir = os.path.join(report_dir, 'logs')
bulkext_dir = os.path.join(report_dir, 'bulk_extractor')
sf_file = os.path.join(report_dir, 'siegfried.csv')

# create directory for reports
try:
	os.makedirs(report_dir)
except OSError as exception:
	if exception.errno != errno.EEXIST:
		raise
	
# create subdirectory for CSV reports
try:
	os.makedirs(csv_dir)
except OSError as exception:
	if exception.errno != errno.EEXIST:
		raise

# create subdirectory for logs if needed
if args.bulkextractor == False and args.noclam == True:
	pass
else:
	try:
		os.makedirs(log_dir)
	except OSError as exception:
		if exception.errno != errno.EEXIST:
			raise

# create html report
temp_html = os.path.join(report_dir, 'temp.html')
html = open(temp_html, 'wb')

# open sqlite db
db = os.path.join(report_dir, 'siegfried.sqlite')
conn = sqlite3.connect(db)
conn.text_factory = str  # allows utf-8 data to be stored
cursor = conn.cursor()

# characterize source
if args.diskimage == True: # source is a disk image
	# make tempdir
	tempdir = os.path.join(report_dir, 'carved_files')
	try:
		os.makedirs(tempdir)
	except OSError as exception:
		if exception.errno != errno.EEXIST:
			raise

	# export disk image contents to tempdir
	if args.hfs == True: # hfs disks
		carvefiles = "bash /usr/share/hfsexplorer/bin/unhfs.sh -o '%s' '%s'" % (tempdir, args.source)
		print("\nAttempting to carve files from disk image using HFS Explorer.")
		try:
			subprocess.call(carvefiles, shell=True)
			print("\nFile carving successful.")
		except subprocess.CalledProcessError as e:
			print(e.output)
			print("\nBrunnhilde was unable to export files from disk image. Ending process.")
			shutil.rmtree(report_dir)
			sys.exit()

	else: # non-hfs disks (note: no UDF support yet)
		carvefiles = ['tsk_recover', '-a', args.source, tempdir]
		print("\nAttempting to carve files from disk image using tsk_recover.")
		try:
			subprocess.check_output(carvefiles)
			print("\nFile carving successful.")
		except subprocess.CalledProcessError as e:
			print(e.output)
			print("\nBrunnhilde was unable to export files from disk image. Ending process.")
			shutil.rmtree(report_dir)
			sys.exit()

	# process tempdir
	if args.noclam == False: # run clamAV virus check unless specified otherwise
		run_clamav(tempdir)
	process_content(tempdir)
	if args.bulkextractor == True: # bulk extractor option is chosen
		run_bulkext(tempdir)
		write_html('Personally Identifiable Information (PII)', '%s/pii.txt' % bulkext_dir, '\t')
	if args.removefiles == True:
		shutil.rmtree(tempdir)


else: #source is a directory
	if os.path.isdir(args.source) == False:
		print("\nSource is not a Directory. If you're processing a disk image, place '-d' before source.")
		sys.exit()
	if args.noclam == False: # run clamAV virus check unless specified otherwise
		run_clamav(args.source)
	process_content(args.source)
	if args.bulkextractor == True: # bulk extractor option is chosen
		run_bulkext(args.source)
		write_html('Personally Identifiable Information (PII)', '%s/pii.txt' % bulkext_dir, '\t')

# close HTML file
html.close()

# write new html file, with hrefs for PRONOM IDs
new_html = os.path.join(report_dir, '%s.html' % basename)
with open(temp_html, 'rb') as in_file:
	with open(new_html, 'wb') as out_file:
		for line in in_file:
			if line.startswith('<td>x-fmt/') or line.startswith('<td>fmt/'):
				puid = line.replace('<td>', '')
				puid = puid.replace('</td>', '')
				newline = '<td><a href="http://apps.nationalarchives.gov.uk/PRONOM/%s" target="_blank">%s</a></td>' % (puid, puid)
				out_file.write(newline)
			else:
				out_file.write(line)

# remove temp html file
os.remove(temp_html)

# close database connections
cursor.close()
conn.close()

print("\nProcess complete. Reports in %s." % report_dir)
