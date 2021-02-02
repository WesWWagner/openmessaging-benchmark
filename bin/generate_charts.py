#!/usr/bin/env python3
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#

import json
import sys
import statistics
import math
import numpy as np
import argparse
import re
import pygal
from pygal.style import Style
from itertools import chain
from os import walk
from os import path
from jinja2 import Template
from collections import defaultdict

graph_colors = ['#202020', # dark gray 
                '#0000ff', # blue 
                '#ff0000', # red
                '#00ff00', 
                '#ff00ff', 
                '#ffff00', 
                '#00ffff', 
                '#ffd700']
chartStyle = Style(
    background='transparent',
    plot_background='transparent',
    font_family='googlefont:Montserrat',
    colors=graph_colors,
    label_font_size=16,
    legend_font_size=16,
    major_label_font_size=16,
)

#theme = pygal.style.CleanStyle
theme = chartStyle
fill = False
output = ''
file_list = defaultdict(list)

def _clean_xy_values(values):
    values = sorted((float(x), y) for x, y in values.items())
    # do not restrict to any percentiles. show the max; the outliers
    # are where the goodies lie
    def _x_axis(x):
        if x < 100: 
            return math.log10(100 / (100 - x))
        return x
    xy_values = [(_x_axis(x), y) for x, y in values]
    found_normalized_max = False
    def _max_index(clean_vals):
        index = 0
        for x, y in clean_vals:
            if 100 == int(x): return index
            index = index + 1
    return xy_values[:_max_index(xy_values)]


def create_quantile_chart(prefix, workload, title, y_label, time_series):
    def _fmt_val(x):
        return '{:,.3f}%'.format(100.0 - (100.0 / (10**x)))
    chart = pygal.XY(style=theme,
                     dots_size=2,
                     legend_at_bottom=True,
                     truncate_legend=37,
                     x_value_formatter=_fmt_val,
                     show_dots=True,
                     fill=fill,
                     stroke_style={'width': 2},
                     show_y_guides=True,
                     show_x_guides=True)
    # chart = pygal.XY()
    chart.title = title
    chart.human_readable = True
    chart.y_title = y_label
    chart.x_title = 'Percentile'
    chart.x_labels = [1, 3, 5, 8]
    for label, values, opts in time_series:
        xy_values = _clean_xy_values(values)    
        chart.add(label, xy_values, stroke_style=opts)

    file_list[prefix].append(f'{workload}.svg')
    chart.render_to_file(f'{output}{workload}.svg')


def create_multi_chart(prefix, svg_file_name, title, y_label_1, y_label_2,
                       time_series):
    chart = pygal.XY(style=theme,
                     dots_size=1,
                     show_dots=False,
                     stroke_style={'width': 2},
                     fill=fill,
                     legend_at_bottom=True,
                     show_x_guides=False,
                     show_y_guides=True)
    chart.title = title
    chart.human_readable = True
    chart.x_title = 'Time (seconds)'

    ys_1 = []
    ys_2 = []

    for label_1, values_1, label_2, values_2 in time_series:
        ys_1.append(values_1)
        chart.add(label_1, [(10 * x, y) for x, y in enumerate(values_1)])
        chart.add(label_2, [(10 * x, y) for x, y in enumerate(values_2)],
                  secondary=True)

    ys_1 = chain.from_iterable(ys_1)
    ys_2 = chain.from_iterable(ys_2)
    max_y_1 = float('-inf')  # Hack for starting w/ INT64_MIN
    max_y_2 = max_y_1
    for y in ys_1:
        if max_y_1 < y:
            max_y_1 = y
    chart.range = (0, max_y_1 * 1.20)

    file_list[prefix].append(f'{path.basename(svg_file_name)}.svg')
    chart.render_to_file(f'{svg_file_name}.svg')


def create_bar_chart(prefix, workload, title, y_label, x_label, data):
    chart = pygal.Bar(style=theme,
                      dots_size=1,
                      show_dots=False,
                      stroke_style={'width': 2},
                      fill=fill,
                      show_legend=False,
                      show_x_guides=False,
                      show_y_guides=True)
    chart.title = title
    chart.x_labels = x_label
    chart.value_formatter = lambda y: "{:,.0f}".format(y)

    for label, points in data.items():
        chart.add(label, points)

    file_list[prefix].append(f'{workload}.svg')
    chart.render_to_file(f'{output}{workload}.svg')


def create_chart(prefix, workload, title, y_label, time_series):
    chart = pygal.XY(style=theme,
                     dots_size=1,
                     show_dots=False,
                     stroke_style={'width': 2},
                     fill=fill,
                     legend_at_bottom=True,
                     show_x_guides=False,
                     show_y_guides=True)
    chart.title = title

    chart.human_readable = True
    chart.y_title = y_label
    chart.x_title = 'Time (seconds)'
    
    ys = []
    for label, values in time_series:
        ys.append(values)
        chart.add(label, [(10 * x, y) for x, y in enumerate(values)])
    ys = chain.from_iterable(ys)
    max_y = float('-inf')  # Hack for starting w/ INT64_MIN
    for y in ys:
        if max_y < y:
            max_y = y
    chart.range = (max_y * 0.0, max_y * 1.20)

    file_list[prefix].append(f'{workload}.svg')
    chart.render_to_file(f'{output}{workload}.svg')


def generate_charts(files):

    aggregate = []
    topics = 0
    partitions = 0
    message_size = 0
    producers = 0
    rate = 0

    for file in sorted(files):
        data = json.load(open(file))
        m = re.search(
            r'^(\d+)-topic-(\d+)-partitions-(\d+)kb-(\d+)-producers-(\d+)k-rate-(\w+)-.*',
            path.basename(file))
        if m:
            topic = m.group(1)
            partitions = m.group(2)
            message_size = m.group(3)
            producers = m.group(4)
            rate = m.group(5)
            data['file'] = m.group(6)
        else:
            print("Something is not right with the file names!")
            exit(-1)
        aggregate.append(data)

    stats_pub_rate = []
    stats_con_rate = []
    stats_backlog = []
    stats_lat_p99 = []
    stats_lat_p999 = []
    stats_lat_p9999 = []
    stat_lat_avg = []
    stat_lat_max = []
    stat_lat_quantile = []
    stat_e2e_lat_quantile = []
    drivers = []

    pub_rate_avg = {}
    pub_rate_avg["Throughput (MB/s): higher is better"] = []

    # Aggregate across all runs
    count = 0
    for data in aggregate:
        stats_pub_rate.append(data['publishRate'])
        stats_con_rate.append(data['consumeRate'])
        stats_backlog.append(data['backlog'])
        stats_lat_p99.append(data['publishLatency99pct'])
        stats_lat_p999.append(data['publishLatency999pct'])
        stats_lat_p9999.append(data['publishLatency9999pct'])
        stat_lat_avg.append(data['publishLatencyAvg'])
        stat_lat_max.append(data['publishLatencyMax'])

        stat_lat_quantile.append(data['aggregatedPublishLatencyQuantiles'])
        stat_e2e_lat_quantile.append(
            data['aggregatedEndToEndLatencyQuantiles'])
        drivers.append(data['file'])
        pub_rate_avg["Throughput (MB/s): higher is better"].append({
            'value':
            (sum(data['publishRate']) / len(data['publishRate']) * 1024) /
            (1024.0 * 1024.0),
            'color':
            graph_colors[count % len(graph_colors)]
        })
        count = count + 1

    # Parse plot options
    opts = []
    if args.opts is None:
        for driver in drivers:
            opts.append({})
    else:
        for opt in args.opts:
            if opt == 'Dashed':
                opts.append({'width': 2, 'dasharray': '3, 6, 12, 24'})
            else:
                opts.append({})

    prefix = f'{rate}k-rate-{partitions}-partitions-{message_size}kb-{producers}-producers'

    # Generate publish rate bar-chart
    svg = prefix + '-publish-rate-bar'
    create_bar_chart(prefix, svg, 'Throughput (MB/s): higher is better', 'MB/s', drivers,
                     pub_rate_avg)

    # Generate latency quantiles
    time_series = zip(drivers, stat_lat_quantile, opts)
    svg = prefix + '-latency-quantile'
    create_quantile_chart(prefix,
                          svg,
                          'Publish Latency Percentiles: lower is better',
                          y_label='Latency (ms)',
                          time_series=time_series)

    time_series = zip(drivers, stat_e2e_lat_quantile, opts)
    svg = prefix + '-e2e-latency-quantile'
    create_quantile_chart(prefix,
                          svg,
                          'End-to-End Latency Percentiles: lower is better',
                          y_label='Latency (ms)',
                          time_series=time_series)

    # Generate p99 latency time-series
    svg = prefix + '-publish-latency-p99'
    time_series = zip(drivers, stats_lat_p99)
    create_chart(prefix,
                 svg,
                 'Publish Latency - 99th Percentile: lower is better',
                 y_label='Latency (ms)',
                 time_series=time_series)

    # Generate avg E2E latency time-series
    svg = prefix + '-e2e-latency-avg'
    time_series = zip(drivers, stat_lat_avg)
    create_chart(prefix,
                 svg,
                 'End-to-end Latency - Average: lower is better',
                 y_label='Latency (ms)',
                 time_series=time_series)

    # Generate publish rate
    svg = prefix + '-publish-rate'
    time_series = zip(drivers, stats_pub_rate)
    create_chart(prefix,
                 svg,
                 'Publish Rate: higher is better',
                 y_label='Message/s',
                 time_series=time_series)

    # Generate consume + backlog rate
    svg = f'{output}{prefix}-consume-rate-backlog'
    labels_con = []
    labels_backlog = []

    for x in drivers:
        labels_con.append(x + " - Consume Rate")
        labels_backlog.append(x + " - Backlog")

    time_series = zip(labels_con, stats_con_rate, labels_backlog,
                      stats_backlog)
    create_multi_chart(
        prefix, svg,
        'Consume rate (Messages/s - Left) w/ Backlog (No. of Messages - Right)',
        'Consume - Messages/s', 'Backlog - Messages', time_series)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Plot Kafka OpenMessaging Benchmark results')

    parser.add_argument(
        '--results',
        dest='results_dir',
        required=True,
        help='Directory containing the results for both Redpanda and Kafka')
    parser.add_argument('--series-opts',
                        nargs='+',
                        dest='opts',
                        required=False,
                        type=str,
                        help='Options for each series: Dashed or Filled')
    parser.add_argument('--output',
                        dest='output',
                        required=False,
                        type=str,
                        help='Location where all output will be stored')
    args = parser.parse_args()

    prefixes = {}

    if args.output != '':
        output = path.join(args.output, '')

    # Get list of directories
    for (dirpath, dirnames, filenames) in walk(args.results_dir):
        for file in filenames:
            m = re.search(
                r'(^\d+-topic-\d+-partitions-\d+kb-\d+-producers-\d+k-rate-).*',
                file)
            if m:
                prefix = m.group(1)
                file_path = path.join(dirpath, file)
                if prefix in prefixes:
                    prefixes[prefix].append(file_path)
                else:
                    prefixes[prefix] = [file_path]

    for prefix in prefixes:
        generate_charts(prefixes[prefix])

    html = '''
<html>
<head>

<link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css">
</head>
<body >
<div class="container">
<h1> {{title}} </h1>
{% for prefix in file_list %}
    <div class='row'>
    <div class='well col-md-12'><h2>{{prefix}}<h2></div>
    {% for file in file_list[prefix] %}
        <div class="embed-responsive embed-responsive-4by3">
            <embed class=embed-responsive-item" type="image/svg+xml" src="{{file}}"/>
        </div>
    {% endfor %}
    <div>
{% endfor %}
</div>
</body>
</html>
    '''

    template = Template(html)

    index_html = template.render(file_list=file_list, title="Charts")

    f = open(f"{output}index.html", "w")
    f.write(index_html)
    f.close()