"""
ncOrtho - Targeted ortholog search for miRNAs
Copyright (C) 2021 Felix Langschied

ncOrtho is a free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

ncOrtho is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with ncOrtho.  If not, see <http://www.gnu.org/licenses/>.
"""


# Modules import
import argparse
import multiprocessing as mp
import os
import subprocess as sp
import sys

# Internal ncOrtho modules
try:
    from ncOrtho.blastparser import BlastParser
    from ncOrtho.blastparser import ReBlastParser
    from ncOrtho.genparser import GenomeParser
    from ncOrtho.cmsearch import cmsearcher
    from ncOrtho.utils import check_blastdb
    from ncOrtho.utils import make_blastndb
except ImportError:
    from blastparser import BlastParser
    from blastparser import ReBlastParser
    from genparser import GenomeParser
    from cmsearch import cmsearcher
    from utils import check_blastdb
    from utils import make_blastndb

###############################################################################


# Central class of microRNA objects
class Mirna(object):
    def __init__(self, name, chromosome, start, end, strand, pre, mature, bit):
        # miRNA identifier
        self.name = name
        # chromosome that the miRNA is located on
        if chromosome.startswith('chr'):
            self.chromosome = chromosome.split('chr')[1]
        else:
            self.chromosome = chromosome
        # start position of the pre-miRNA
        self.start = int(start)
        # end position of the pre-miRNA
        self.end = int(end)
        # sense (+) or anti-sense (-) strand
        self.strand = strand
        # nucleotide sequence of the pre-miRNA
        self.pre = pre.replace('U', 'T')
        # nucleotide sequence of the mature miRNA
        self.mature = mature.replace('U', 'T')
        # reference bit score that miRNA receives by its own
        # covariance model
        self.bit = bit


def mirna_maker(mirpath, cmpath, output, msl):
    """
    Parses the miRNA data input file and returns a dictionary of Mirna objects.

    Parameters
    ----------
    mirpath : STR
        Path to file with microRNA data.
    cmpath : STR
        Path to covariance models.
    output : STR
        Path for writing temporary files.
    msl : FLOAT
        Length filter.

    Returns
    -------
    mmdict : DICT
        Dictionary with Mirna objects.

    """
    
    mmdict = {} # will be the return object
    
    with open(mirpath) as mirna_file:
        mirna_data = [
            line.strip().split() for line in mirna_file
            if not line.startswith('#')
        ]

    for mirna in mirna_data:
        mirid = mirna[0]
        seq = mirna[5]
        query = '{0}/{1}.fa'.format(output, mirid)
        model = '{0}/{1}.cm'.format(cmpath, mirid)
        # Check if the covariance model even exists, otherwise skip to
        # the next miRNA.
        if not os.path.isfile(model):
            print('# No covariance model found for {}'.format(mirid))
            continue
        # Check if the output folder exists, otherwise create it.
        if not os.path.isdir('{}'.format(output)):
            mkdir = 'mkdir -p {}'.format(output)
            sp.call(mkdir, shell=True)


        # Obtain the reference bit score for each miRNA by applying it
        # to its own covariance model.
        print('# Calculating reference bit score for {}.'.format(mirid))
        
        # Create a temporary FASTA file with the miRNA sequence as
        # query for external search tool cmsearch to calculate the
        # reference bit score.
        with open(query, 'w') as tmpfile:
            tmpfile.write('>{0}\n{1}'.format(mirid, seq))
        cms_output = '{0}/ref_cmsearch_{1}_tmp.out'.format(output, mirid)
        cms_log = '{0}/ref_cmsearch_{1}.log'.format(output, mirid)
        if not os.path.isfile(cms_output):
            cms_command = (
                'cmsearch -E 0.01 --noali -o {3} --tblout {0} {1} {2}'
                .format(cms_output, model, query, cms_log)
            )
            sp.call(cms_command, shell=True)
        else:
            print('# Found cmsearch results at: {} using those'.format(cms_output))
        with open(cms_output) as cmsfile:
            hits = [
                line.strip().split() for line in cmsfile
                if not line.startswith('#')
            ]
            if hits:
                top_score = float(hits[0][14])
            # In case of any issues occuring in the calculation of the bit
            # score, no specific threshold can be determined. The value will
            # set to zero, which technically turns off the filter.
            else:
                print(
                    '# Warning: Self bit score not applicable, '
                    'setting threshold to 0.'
                )
                top_score = 0.0

        mirna.append(top_score)

        # Remove temporary files.
        for rmv_file in [cms_output, cms_log, query]:
            sp.call('rm {}'.format(rmv_file), shell=True)

        # Create output.
        mmdict[mirna[0]] = Mirna(*mirna)

    return mmdict


# Allow boolean argument parsing
def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


# Main function
def main():

    # Print header
    print('\n'+'#'*57)
    print('###'+' '*51+'###')
    print('###   ncOrtho - ortholog search for non-coding RNAs   ###')
    print('###'+' '*51+'###')
    print('#'*57+'\n')
    
    # Parse command-line arguments
    # Define global variables
    parser = argparse.ArgumentParser(
        description='Find orthologs of reference miRNAs in the genome of a query species.'
    )
    parser._action_groups.pop()
    required = parser.add_argument_group('Required Arguments')
    optional = parser.add_argument_group('Optional Arguments')
    # covariance models folder
    required.add_argument(
        '-m', '--models', metavar='<path>', type=str, required=True,
        help='Path to directory containing covariance models (.cm)'
    )
    # mirna data
    required.add_argument(
        '-n', '--ncrna', metavar='<path>', type=str, required=True,
        help='Path to Tab separated file with information about the reference miRNAs'
    )
    # output folder
    required.add_argument(
        '-o', '--output', metavar='<path>', type=str, required=True,
        help='Path to the output directory'
    )
    # query genome
    required.add_argument(
        '-q', '--query', metavar='<.fa>', type=str, required=True,
        help='Path to query genome in FASTA format'
    )
    # reference genome
    required.add_argument(
        '-r', '--reference', metavar='<.fa>', type=str, required=True,
        help='Path to reference genome in FASTA format'
    )
    ##########################################################################
    # Optional Arguments
    ##########################################################################
    # query_name
    optional.add_argument(
        '--queryname', metavar='str', type=str, nargs='?', const='', default='',
        help=(
            'Name for the output directory '
            '(Use this if you run ncOrtho for multiple taxa whose genome file has the same name)'
        )
    )
    # cpu, use maximum number of available cpus unless specified otherwise
    optional.add_argument(
        '--cpu', metavar='int', type=int,
        help='Number of CPU cores to use (Default: all available)', nargs='?',
        const=mp.cpu_count(), default=mp.cpu_count()
    )
    # bit score cutoff for cmsearch hits
    optional.add_argument(
        '--cm_cutoff', metavar='float', type=float,
        help='CMsearch bit score cutoff, given as ratio of the CMsearch bitscore '
             'of the CM against the refernce species (Default: 0.5)', nargs='?', const=0.5, default=0.5
    )
    # length filter to prevent short hits
    optional.add_argument(
        '--minlength', metavar='float', type=float,
        help='CMsearch hit in the query species must have at '
             'least the length of this value times the length of the refernce pre-miRNA (Default: 0.7)',
        nargs='?', const=0.7, default=0.7
    )
    optional.add_argument(
        '--heuristic', type=str2bool, metavar='True/False', nargs='?', const=True, default=True,
        help=(
            'Perform a BLAST search of the reference miRNA in the query genome to identify '
            'candidate regions for the CMsearch. Majorly improves speed. (Default: True)'
        )
    )
    optional.add_argument(
        '--heur_blast_evalue', type=float, metavar='float', nargs='?', const=0.5, default=0.5,
        help=(
            'Evalue filter for the BLASTn search that '
            'determines candidate regions for the CMsearch when running ncOrtho in heuristic mode. '
            '(Default: 0.5) (Set to 10 to turn off)'
        )
    )
    optional.add_argument(
        '--heur_blast_length', type=float, metavar='float', nargs='?', const=0.5, default=0.5,
        help=(
            'Length cutoff for BLASTN search with which candidate regions for the CMsearch are identified.'
            'Cutoff is given as ratio of the reference pre-miRNA length '
            '(Default: 0.5) (Set to 0 to turn off)'
        )
    )
    optional.add_argument(
        '--cleanup', type=str2bool, metavar='True/False', nargs='?', const=True, default=True,
        help=(
            'Cleanup temporary files (Default: True)'
        )
    )
    optional.add_argument(
        '--refblast', type=str, metavar='<path>', nargs='?', const='', default='',
        help=(
            'Path to BLASTdb of the reference species'
        )
    )
    optional.add_argument(
        '--queryblast', type=str, metavar='<path>', nargs='?', const='', default='',
        help=(
            'Path to BLASTdb of the query species'
        )
    )
    optional.add_argument(
        '--maxcmhits', metavar='int', nargs='?', const=50, default=50,
        help=(
            'Maximum number of cmsearch hits to examine. '
            'Decreases runtime significantly if reference miRNA in genomic repeat region (Default: 50). '
            'Set to empty variable to disable (i.e. --maxcmhits="")'
        )
    )
    # use dust filter?
    parser.add_argument(
        '--dust', metavar='yes/no', type=str,
        help='Use BLASTn dust filter during re-BLAST. Greatly decreases runtime if reference miRNA(s) '
             'are located in repeat regions. '
             'However ncOrtho will also not identify orthologs for these miRNAs',
        nargs='?',
        const='no', default='no'
    )
    # check Co-ortholog-ref
    parser.add_argument(
        '--checkCoorthologsRef', type=str2bool, metavar='True/False', nargs='?', const=False, default=False,
        help=(
            'If the re-blast does not identify the original reference miRNA sequence as best hit,'
            'ncOrtho will check whether the best blast '
            'hit is likely a co-ortholog of the reference miRNA relative to the search taxon. '
            'NOTE: Setting this flag will substantially increase'
            'the sensitivity of HaMStR but most likely affect also the specificity, '
            'especially when the search taxon is evolutionarily only very'
            'distantly related to the reference taxon (Default: False)'
        )
    )

    # Show help when no arguments are added.
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)
    else:
        args = parser.parse_args()
    
    # Check if computer provides the desired number of cores.
    available_cpu = mp.cpu_count()
    if args.cpu > available_cpu:
        print(
            '# Error: The provided number of CPU cores is higher than the '
            'number available on this system. Exiting...'
        )
        sys.exit(1)
    else:
        cpu = args.cpu

    mirnas = args.ncrna
    models = args.models
    output = args.output
    query = args.query
    reference = args.reference

    # optional
    max_hits = args.maxcmhits
    cm_cutoff = args.cm_cutoff
    checkCoorthref = args.checkCoorthologsRef
    cleanup = args.cleanup
    heuristic = (args.heuristic, args.heur_blast_evalue, args.heur_blast_length)
    msl = args.minlength
    refblast = args.refblast
    qblast = args.queryblast
    dust = args.dust.strip()

    ##########################################################################################
    # Starting argument checks
    ##########################################################################################

    # Test if optional query name was given
    if args.queryname:
        qname = args.queryname
    else:
        qname = '.'.join(query.split('/')[-1].split('.')[:-1])
    # make folder for query in output dir
    if not output.split('/')[-1] == qname:
        output = f'{output}/{qname}'

    # Test if input files exist
    all_files = [mirnas, reference, query]
    for pth in all_files:
        if not os.path.isfile(pth):
            print(f'ERROR: {pth} is not a file')
            sys.exit()
    if not os.path.isdir(models):
        print(f'ERROR: Directory with covariance models does not exist at: {models}')
        sys.exit()

    # create symbolic links to guarantee writing permissions
    q_data = '{}/data'.format(output)
    if not os.path.isdir(q_data):
        os.makedirs(q_data)
    qlink = f'{q_data}/{qname}.fa'
    try:
        os.symlink(query, qlink)
    except FileExistsError:
        pass

    # check if reference BLASTdb was given as input
    if refblast:
        # check if BLASTdb exists
        if not check_blastdb(refblast):
            print('# Reference BLASTdb not found at: {}'.format(refblast))
            sys.exit()
    else:
        refname = reference.split('/')[-1]
        refblast = f'{q_data}/{refname}'
        # check if BLASTdb exists already. Otherwise create it
        if not check_blastdb(refblast):
            make_blastndb(reference, refblast)
    # check if query BLASTdb was given as input (only used in heuristic mode)
    if qblast and heuristic:
        # check if qblast exists
        if not check_blastdb(qblast):
            print('# Query BLASTdb not found at: {}'.format(qblast))
            sys.exit()
    elif heuristic:
        qblast = qlink
        # check if already exists
        if not check_blastdb(qlink):
            print('# Creating query Database')
            make_blastndb(query, qlink)

    ################################################################################################
    # Main
    ###############################################################################################

    # Print out query
    print('### Starting ncOrtho run for {}'.format(query))

    # Create miRNA objects from the list of input miRNAs.
    mirna_dict = mirna_maker(mirnas, models, output, msl)

    # Identify ortholog candidates.
    for mir_data in mirna_dict:
        sys.stdout.flush()
        mirna = mirna_dict[mir_data]
        mirna_id = mirna.name

        # Create output folder, if not existent.
        if heuristic:
            outdir = '{}'.format(output)
        else:
            outdir = '{}/{}'.format(output, mirna_id)
        if not os.path.isdir(outdir):
            os.makedirs(outdir)

        # start cmsearch
        cm_results = cmsearcher(mirna, cm_cutoff, cpu, msl, models, qlink, qblast, output, cleanup, heuristic)

        # Extract sequences for candidate hits (if any were found).
        if not cm_results:
            print('# No hits found for {}.\n'.format(mirna_id))
            continue
        elif max_hits and len(cm_results) > max_hits:
            print('# Maximum CMsearch hits reached. Restricting to best {} hits'.format(max_hits))
            cm_results = {k: cm_results[k] for k in list(cm_results.keys())[:max_hits]}
        # get sequences for each CM result
        gp = GenomeParser(qlink, cm_results.values())
        candidates = gp.extract_sequences()
        nr_candidates = len(candidates)
        if nr_candidates == 1:
            print(
                '\n# Covariance model search successful, found 1 '
                'ortholog candidate.\n'
            )
        else:
            print(
                '\n# Covariance model search successful, found {} '
                'ortholog candidates.\n'
                .format(nr_candidates)
            )
        print('# Evaluating candidates.\n')
        
        # Perform reverse BLAST test to verify candidates, stored in
        # a list (accepted_hits).
        reblast_hits = {}
        for candidate in candidates:
            sequence = candidates[candidate]
            temp_fasta = '{0}/{1}.fa'.format(outdir, candidate)
            with open(temp_fasta, 'w') as tempfile:
                tempfile.write('>{0}\n{1}\n'.format(candidate, sequence))
            blast_output = '{0}/blast_{1}.out'.format(outdir, candidate)
            print('# Starting reverse blast for {}'.format(candidate))
            # blast_search will write results to the temp_fasta file
            blast_command = (
                'blastn -task blastn -db {0} -query {1} -max_target_seqs 10 -dust {4} '
                '-out {2} -num_threads {3} -outfmt "6 qseqid sseqid pident '
                'length mismatch gapopen qstart qend sstart send evalue bitscore sseq"'
                    .format(refblast, temp_fasta, blast_output, cpu, dust)
            )
            sp.run(blast_command, shell=True)
            print('# finished blast')

            # BlastParser will read the temp_fasta file
            bp = BlastParser(mirna, blast_output, msl)
            # the parse_blast_output function will return True if the candidate is accepted
            if bp.evaluate_besthit():
                print('Found best hit')
                reblast_hits[candidate] = sequence
            elif checkCoorthref:
                print('Best hit differs from reference sequence! Doing further checks\n')
                # coorth_out = '{0}/{1}_coorth'.format(outdir, candidate)
                if bp.check_coortholog_ref(sequence, outdir):
                    reblast_hits[candidate] = sequence
            else:
                print('Best hit does not overlap with miRNA location')
            if cleanup:
                os.remove(temp_fasta)
                os.remove(blast_output)

        # Write output file if at least one candidate got accepted.
        if reblast_hits:
            nr_accepted = len(reblast_hits)
            if nr_accepted == 1:
                print('# ncOrtho found 1 verified ortholog.\n')
                out_dict = reblast_hits
            else:
                print(
                    '# ncOrtho found {} potential co-orthologs.\n'
                    .format(nr_accepted)
                )
                print('# Evaluating distance between candidates to verify co-orthologs')
                rbp = ReBlastParser(mirna, reblast_hits)
                out_dict = rbp.verify_coorthologs(outdir)
                if len(out_dict) == 1:
                    print('ncOrtho found 1 verified ortholog')
                else:
                    print(
                        '# ncOrtho found {} verified co-orthologs.\n'
                            .format(len(out_dict))
                    )

            print('# Writing output of accepted candidates.\n')
            outpath = '{0}/{1}_orthologs.fa'.format(outdir, mirna_id)
            with open(outpath, 'w') as of:
                for hit in out_dict:
                    cmres = list(cm_results[hit])
                    cmres.insert(qname)
                    header = '|'.join(cmres)
                    of.write('>{0}\n{1}\n'.format(header, out_dict[hit]))

            # write_output(out_dict, outpath, cm_results)
            print('# Finished writing output.\n')
        else:
            print(
                '# None of the candidates for {} could be verified.\n'
                .format(mirna_id)
            )
        print('# Finished ortholog search for {}.'.format(mirna_id))
    print('### ncOrtho is finished!')


if __name__ == "__main__":
    main()
