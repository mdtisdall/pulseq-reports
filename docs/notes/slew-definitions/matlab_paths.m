% The MATLAB Pulseq paths of docs/notes/slew-definitions.md, run in GNU Octave by
% slew_paths.py. For each example .seq file listed in examples.txt of OUT_DIR, it
% writes <name>_matlab.mat with:
%
%   gw_x, gw_y, gw_z  the merged waveform of waveforms_and_times() (2 x n: s, Hz/m)
%   t_axis, gwr       the sample times and samples (Hz/m) of calcPNS
%   dgdt              the SAFE input that calcPNS keeps (3 x n, T/m/s)
%   pns_copy          the PNS of these same lines (3 x n, fraction of the limit)
%   ok, pns_norm, pns_comp, t_pns   the outputs of seq.calcPNS itself
%   report_slew       the per-axis "Max. Slew Rate" of testReport (T/m/s), computed
%                     with the same lines as testReport.m (gws = diff(g) ./ diff(t))
%   warnings          the warnings that waveforms_and_times() gave
%   pns_norm_old      for the example "epi" only: calcPNS with example_hw_old_layout.asc

addpath(getenv('PULSEQ_MATLAB'));
addpath(getenv('SAFE_MATLAB'));
warning('off', 'Octave:function-name-clash');
warning('off', 'Octave:possible-matlab-short-circuit-operator');
out_dir = getenv('OUT_DIR');
names = strsplit(strtrim(fileread(fullfile(out_dir, 'examples.txt'))), "\n");
asc = fullfile(out_dir, 'example_hw.asc');
sys = mr.opts('MaxGrad', 40, 'GradUnit', 'mT/m', 'MaxSlew', 100, 'SlewUnit', 'T/m/s');
% The same values as example_hw.asc. safe_example_hw_peripheral.m defines a function
% named safe_example_hw, hence the name clash warning that is turned off above.
hw = safe_example_hw_peripheral();

for i = 1:numel(names)
  name = strtrim(names{i});
  seq = mr.Sequence(sys);
  seq.read(fullfile(out_dir, [name '.seq']));

  lastwarn('');
  gw = seq.waveforms_and_times();
  [msg, ~] = lastwarn();
  warnings = msg;

  % The PNS as MATLAB Pulseq computes it.
  [ok, pns_norm, pns_comp, t_pns] = seq.calcPNS(asc, false);

  pns_norm_old = [];
  if strcmp(name, 'epi')
    [~, pns_norm_old] = seq.calcPNS(fullfile(out_dir, 'example_hw_old_layout.asc'), false);
  end

  % The same lines as calcPNS.m (pulseq/pulseq, matlab/+mr/@Sequence/calcPNS.m), but
  % keeping res.dgdt.
  tf = []; tl = [];
  for k = 1:3
    if size(gw{k}, 2) > 0
      tf(end + 1) = gw{k}(1, 1);
      tl(end + 1) = gw{k}(1, end);
    end
  end
  nt_min = floor(min(tf) / seq.gradRasterTime + eps);
  nt_max = ceil(max(tl) / seq.gradRasterTime - eps);
  nt_min = nt_min + 0.5;
  nt_max = nt_max - 0.5;
  if nt_min < 0.5
    nt_min = 0.5;
  end
  t_axis = (nt_min:nt_max) * seq.gradRasterTime;
  gwr = zeros(length(t_axis), 3);
  for k = 1:3
    if size(gw{k}, 2) > 0
      gwr(:, k) = interp1(gw{k}(1, :), gw{k}(2, :), t_axis, 'linear', 0);
    end
  end
  [pns0, res] = safe_gwf_to_pns(gwr / seq.sys.gamma, NaN * ones(length(t_axis), 1), ...
                                seq.gradRasterTime, hw);
  keep = ~isfinite(res.rf);
  pns_copy = 0.01 * pns0(keep, :)';
  dgdt = res.dgdt(keep, :)';
  if max(abs(pns_copy(:) - pns_comp(:))) > 1e-12
    error('%s: the copied calcPNS lines do not give the calcPNS result', name);
  end

  % testReport.m, lines 330-341: the slew of each segment of the merged waveform.
  report_slew = zeros(1, 3);
  for k = 1:3
    if size(gw{k}, 2) > 1
      gws = (gw{k}(2, 2:end) - gw{k}(2, 1:end-1)) ./ (gw{k}(1, 2:end) - gw{k}(1, 1:end-1));
      report_slew(k) = max(abs(gws)) / sys.gamma;
    end
  end

  gw_x = gw{1}; gw_y = gw{2}; gw_z = gw{3};
  save('-v7', fullfile(out_dir, [name '_matlab.mat']), 'gw_x', 'gw_y', 'gw_z', ...
       't_axis', 'gwr', 'dgdt', 'pns_copy', 'ok', 'pns_norm', 'pns_comp', 't_pns', ...
       'report_slew', 'warnings', 'pns_norm_old');
  printf('%s: done\n', name);
end
