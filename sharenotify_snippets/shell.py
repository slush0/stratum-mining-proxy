def on_share(job_id, worker_name, init_time, dif):
    cmd = 'echo [%t] %w %j/%d >> /tmp/sharestats.log'
    cmd = cmd.replace('%j', job_id)
    cmd = cmd.replace('%w', worker_name)
    cmd = cmd.replace('%t', str(init_time))
    cmd = cmd.replace('%d', str(dif))
    log.info("Executing sharenotify command: %s" %cmd)
    subprocess.Popen(cmd, shell=True)
