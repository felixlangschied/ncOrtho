import glob
import subprocess as sp


def check_blastdb(db_path):
    file_extensions = ['nhr', 'nin', 'nsq']
    for fe in file_extensions:
        files = glob.glob(f'{db_path}*{fe}')
        if not files:
            # At least one of the BLAST db files is not existent
            return False
    return True

def make_blastndb(inpath, outpath):
    db_command = 'makeblastdb -in {} -out {} -dbtype nucl'.format(inpath, outpath)
    sp.call(db_command, shell=True)
