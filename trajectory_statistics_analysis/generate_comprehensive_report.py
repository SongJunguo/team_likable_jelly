#!/usr/bin/env python3
"""
Comprehensive Trajectory Completeness Report Generator
=====================================================

This script generates a comprehensive report combining all trajectory completeness analyses:
1. Basic trajectory statistics
2. Official flight data matching results
3. Altitude-based completeness analysis
4. Airport proximity analysis
5. Final recommendations

Author: AI Assistant
Date: 2024
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import json
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

class ComprehensiveReportGenerator:
    """Generate comprehensive trajectory completeness analysis report"""
    
    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.output_dir = self.base_dir / "comprehensive_analysis"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Data sources
        self.stats_file = self.base_dir / "output" / "trajectory_statistics.parquet"
        self.matching_dir = self.base_dir / "matching_analysis"
        self.completeness_dir = self.base_dir / "completeness_analysis"
        self.airport_dir = self.base_dir / "airport_completeness_analysis"
        
    def load_all_data(self):
        """Load data from all analysis components"""
        print("📊 Loading data from all analysis components...")
        
        data = {}
        
        # 1. Basic trajectory statistics
        if self.stats_file.exists():
            data['trajectory_stats'] = pd.read_parquet(self.stats_file)
            print(f"✅ Loaded trajectory statistics: {len(data['trajectory_stats']):,} records")
        
        # 2. Matching analysis results
        matching_files = {
            'challenge_set': self.matching_dir / "matched_challenge_set_data.parquet",
            'submission_set': self.matching_dir / "matched_submission_set_data.parquet",
            'final_submission_set': self.matching_dir / "matched_final_submission_set_data.parquet"
        }
        
        data['matching'] = {}
        for name, file_path in matching_files.items():
            if file_path.exists():
                data['matching'][name] = pd.read_parquet(file_path)
                print(f"✅ Loaded {name}: {len(data['matching'][name]):,} records")
        
        # 3. Airport completeness analysis
        airport_file = self.airport_dir / "airport_completeness_analysis.parquet"
        if airport_file.exists():
            data['airport_analysis'] = pd.read_parquet(airport_file)
            print(f"✅ Loaded airport analysis: {len(data['airport_analysis']):,} records")
        
        return data
    
    def analyze_trajectory_quality(self, data):
        """Analyze overall trajectory quality based on all criteria"""
        print("🔍 Analyzing overall trajectory quality...")
        
        analysis = {}
        
        # Basic statistics
        if 'trajectory_stats' in data:
            stats = data['trajectory_stats']
            analysis['basic'] = {
                'total_trajectories': len(stats),
                'short_trajectories': len(stats[stats['point_count'] < 1000]),
                'short_percentage': len(stats[stats['point_count'] < 1000]) / len(stats) * 100,
                'avg_points': stats['point_count'].mean(),
                'avg_duration': stats['duration_hours'].mean(),
                'median_points': stats['point_count'].median(),
                'median_duration': stats['duration_hours'].median()
            }
        
        # Matching analysis summary
        if 'matching' in data:
            total_matched = sum(len(df) for df in data['matching'].values())
            analysis['matching'] = {
                'total_matched_trajectories': total_matched,
                'challenge_set_matched': len(data['matching'].get('challenge_set', [])),
                'submission_set_matched': len(data['matching'].get('submission_set', [])),
                'final_submission_matched': len(data['matching'].get('final_submission_set', []))
            }
            
            # Duration consistency analysis
            if 'challenge_set' in data['matching']:
                df = data['matching']['challenge_set']
                if 'duration_difference_pct' in df.columns:
                    consistent = (abs(df['duration_difference_pct']) <= 10).sum()
                    analysis['matching']['consistent_trajectories'] = consistent
                    analysis['matching']['consistency_rate'] = consistent / len(df) * 100
        
        # Airport proximity analysis
        if 'airport_analysis' in data:
            airport_df = data['airport_analysis']
            analysis['airport'] = {
                'total_analyzed': len(airport_df),
                'near_start_airport': (airport_df['start_distance_km'] <= 50).sum(),
                'near_end_airport': (airport_df['end_distance_km'] <= 50).sum(),
                'both_near_airports': ((airport_df['start_distance_km'] <= 50) & 
                                     (airport_df['end_distance_km'] <= 50)).sum(),
                'avg_start_distance': airport_df['start_distance_km'].mean(),
                'avg_end_distance': airport_df['end_distance_km'].mean()
            }
        
        return analysis
    
    def create_quality_classification(self, data):
        """Create a comprehensive quality classification for trajectories"""
        print("🏷️ Creating comprehensive quality classification...")
        
        if 'trajectory_stats' not in data:
            return pd.DataFrame()
        
        # Start with basic trajectory data
        df = data['trajectory_stats'].copy()
        
        # Initialize quality scores
        df['quality_score'] = 0
        df['quality_factors'] = ''
        
        # Factor 1: Point count (0-3 points)
        df.loc[df['point_count'] >= 5000, 'quality_score'] += 3
        df.loc[(df['point_count'] >= 2000) & (df['point_count'] < 5000), 'quality_score'] += 2
        df.loc[(df['point_count'] >= 1000) & (df['point_count'] < 2000), 'quality_score'] += 1
        
        # Factor 2: Duration (0-2 points)
        df.loc[df['duration_hours'] >= 1.0, 'quality_score'] += 2
        df.loc[(df['duration_hours'] >= 0.5) & (df['duration_hours'] < 1.0), 'quality_score'] += 1
        
        # Factor 3: Matching with official data (0-3 points)
        if 'matching' in data:
            matched_ids = set()
            for dataset in data['matching'].values():
                matched_ids.update(dataset['flight_id'].tolist())
            
            df.loc[df['flight_id'].isin(matched_ids), 'quality_score'] += 3
            df.loc[df['flight_id'].isin(matched_ids), 'quality_factors'] += 'Official_Match;'
        
        # Factor 4: Airport proximity (0-2 points)
        if 'airport_analysis' in data:
            airport_df = data['airport_analysis']
            
            # Near both airports
            both_near = airport_df[
                (airport_df['start_distance_km'] <= 50) & 
                (airport_df['end_distance_km'] <= 50)
            ]['flight_id'].tolist()
            
            # Near one airport
            one_near = airport_df[
                ((airport_df['start_distance_km'] <= 50) | 
                 (airport_df['end_distance_km'] <= 50)) &
                ~((airport_df['start_distance_km'] <= 50) & 
                  (airport_df['end_distance_km'] <= 50))
            ]['flight_id'].tolist()
            
            df.loc[df['flight_id'].isin(both_near), 'quality_score'] += 2
            df.loc[df['flight_id'].isin(both_near), 'quality_factors'] += 'Both_Airports;'
            
            df.loc[df['flight_id'].isin(one_near), 'quality_score'] += 1
            df.loc[df['flight_id'].isin(one_near), 'quality_factors'] += 'One_Airport;'
        
        # Final quality classification
        df['quality_class'] = 'Poor'
        df.loc[df['quality_score'] >= 8, 'quality_class'] = 'Excellent'
        df.loc[(df['quality_score'] >= 6) & (df['quality_score'] < 8), 'quality_class'] = 'Good'
        df.loc[(df['quality_score'] >= 4) & (df['quality_score'] < 6), 'quality_class'] = 'Fair'
        df.loc[(df['quality_score'] >= 2) & (df['quality_score'] < 4), 'quality_class'] = 'Poor'
        
        return df
    
    def create_comprehensive_visualization(self, data, quality_df):
        """Create comprehensive visualization dashboard"""
        print("📊 Creating comprehensive visualization dashboard...")
        
        # Set up the plotting style
        plt.style.use('default')
        sns.set_palette("husl")
        
        fig = plt.figure(figsize=(24, 20))
        
        # 1. Quality distribution pie chart
        ax1 = plt.subplot(4, 4, 1)
        if not quality_df.empty:
            quality_counts = quality_df['quality_class'].value_counts()
            colors = ['#2E8B57', '#4169E1', '#FF6347', '#FFD700']
            wedges, texts, autotexts = ax1.pie(quality_counts.values, 
                                              labels=quality_counts.index,
                                              autopct='%1.1f%%',
                                              colors=colors[:len(quality_counts)])
            ax1.set_title('Overall Trajectory Quality Distribution', fontsize=12, fontweight='bold')
        
        # 2. Point count distribution by quality
        ax2 = plt.subplot(4, 4, 2)
        if not quality_df.empty:
            for quality in quality_df['quality_class'].unique():
                subset = quality_df[quality_df['quality_class'] == quality]
                ax2.hist(subset['point_count'], bins=30, alpha=0.6, 
                        label=f'{quality} ({len(subset)})', density=True)
            ax2.set_xlabel('Point Count')
            ax2.set_ylabel('Density')
            ax2.set_title('Point Count Distribution by Quality')
            ax2.legend()
            ax2.set_xlim(0, 15000)
        
        # 3. Duration distribution by quality
        ax3 = plt.subplot(4, 4, 3)
        if not quality_df.empty:
            for quality in quality_df['quality_class'].unique():
                subset = quality_df[quality_df['quality_class'] == quality]
                ax3.hist(subset['duration_hours'], bins=30, alpha=0.6, 
                        label=f'{quality} ({len(subset)})', density=True)
            ax3.set_xlabel('Duration (hours)')
            ax3.set_ylabel('Density')
            ax3.set_title('Duration Distribution by Quality')
            ax3.legend()
            ax3.set_xlim(0, 8)
        
        # 4. Quality score distribution
        ax4 = plt.subplot(4, 4, 4)
        if not quality_df.empty:
            ax4.hist(quality_df['quality_score'], bins=range(0, 11), alpha=0.7, 
                    color='skyblue', edgecolor='black')
            ax4.set_xlabel('Quality Score')
            ax4.set_ylabel('Frequency')
            ax4.set_title('Quality Score Distribution')
            ax4.set_xticks(range(0, 11))
        
        # 5. Matching analysis summary
        ax5 = plt.subplot(4, 4, 5)
        if 'matching' in data:
            datasets = list(data['matching'].keys())
            counts = [len(data['matching'][ds]) for ds in datasets]
            ax5.bar(datasets, counts, color=['lightblue', 'lightgreen', 'lightcoral'])
            ax5.set_ylabel('Matched Trajectories')
            ax5.set_title('Official Data Matching Results')
            ax5.tick_params(axis='x', rotation=45)
        
        # 6. Duration consistency (if available)
        ax6 = plt.subplot(4, 4, 6)
        if 'matching' in data and 'challenge_set' in data['matching']:
            df = data['matching']['challenge_set']
            if 'duration_difference_pct' in df.columns:
                ax6.hist(df['duration_difference_pct'], bins=50, alpha=0.7, 
                        color='orange', edgecolor='black')
                ax6.axvline(0, color='red', linestyle='--', label='Perfect match')
                ax6.axvline(-10, color='green', linestyle='--', alpha=0.7)
                ax6.axvline(10, color='green', linestyle='--', alpha=0.7, label='±10% threshold')
                ax6.set_xlabel('Duration Difference (%)')
                ax6.set_ylabel('Frequency')
                ax6.set_title('Duration Consistency with Official Data')
                ax6.legend()
                ax6.set_xlim(-100, 100)
        
        # 7. Airport proximity analysis
        ax7 = plt.subplot(4, 4, 7)
        if 'airport_analysis' in data:
            airport_df = data['airport_analysis']
            distances = [
                (airport_df['start_distance_km'] <= 50).sum(),
                (airport_df['end_distance_km'] <= 50).sum(),
                ((airport_df['start_distance_km'] <= 50) & 
                 (airport_df['end_distance_km'] <= 50)).sum()
            ]
            labels = ['Start Near Airport', 'End Near Airport', 'Both Near Airports']
            ax7.bar(labels, distances, color=['lightblue', 'lightgreen', 'orange'])
            ax7.set_ylabel('Number of Trajectories')
            ax7.set_title('Airport Proximity Analysis')
            ax7.tick_params(axis='x', rotation=45)
        
        # 8. Short trajectory analysis
        ax8 = plt.subplot(4, 4, 8)
        if 'trajectory_stats' in data:
            stats = data['trajectory_stats']
            short_counts = []
            thresholds = [500, 1000, 2000, 5000]
            for threshold in thresholds:
                short_counts.append((stats['point_count'] < threshold).sum())
            
            ax8.bar(range(len(thresholds)), short_counts, color='lightcoral')
            ax8.set_xticks(range(len(thresholds)))
            ax8.set_xticklabels([f'<{t}' for t in thresholds])
            ax8.set_xlabel('Point Count Threshold')
            ax8.set_ylabel('Number of Trajectories')
            ax8.set_title('Short Trajectory Analysis')
        
        # 9-12. Summary statistics tables
        ax9 = plt.subplot(4, 4, (9, 12))
        ax9.axis('off')
        
        # Create summary statistics
        summary_text = []
        
        if 'basic' in data.get('analysis', {}):
            basic = data['analysis']['basic']
            summary_text.extend([
                "BASIC TRAJECTORY STATISTICS",
                "=" * 35,
                f"Total trajectories: {basic['total_trajectories']:,}",
                f"Short trajectories (<1000 pts): {basic['short_trajectories']:,} ({basic['short_percentage']:.1f}%)",
                f"Average points per trajectory: {basic['avg_points']:.0f}",
                f"Average duration: {basic['avg_duration']:.2f} hours",
                f"Median points: {basic['median_points']:.0f}",
                f"Median duration: {basic['median_duration']:.2f} hours",
                ""
            ])
        
        if 'matching' in data.get('analysis', {}):
            matching = data['analysis']['matching']
            summary_text.extend([
                "OFFICIAL DATA MATCHING",
                "=" * 25,
                f"Total matched trajectories: {matching['total_matched_trajectories']:,}",
                f"Challenge set matches: {matching['challenge_set_matched']:,}",
                f"Submission set matches: {matching['submission_set_matched']:,}",
                f"Final submission matches: {matching['final_submission_matched']:,}",
                ""
            ])
            
            if 'consistency_rate' in matching:
                summary_text.extend([
                    f"Duration consistency rate: {matching['consistency_rate']:.1f}%",
                    ""
                ])
        
        if 'airport' in data.get('analysis', {}):
            airport = data['analysis']['airport']
            summary_text.extend([
                "AIRPORT PROXIMITY ANALYSIS",
                "=" * 30,
                f"Trajectories analyzed: {airport['total_analyzed']:,}",
                f"Near start airport (≤50km): {airport['near_start_airport']:,}",
                f"Near end airport (≤50km): {airport['near_end_airport']:,}",
                f"Near both airports: {airport['both_near_airports']:,}",
                f"Avg distance to start airport: {airport['avg_start_distance']:.0f} km",
                f"Avg distance to end airport: {airport['avg_end_distance']:.0f} km",
                ""
            ])
        
        if not quality_df.empty:
            quality_summary = quality_df['quality_class'].value_counts()
            summary_text.extend([
                "QUALITY CLASSIFICATION",
                "=" * 25,
                *[f"{quality}: {count:,} ({count/len(quality_df)*100:.1f}%)" 
                  for quality, count in quality_summary.items()],
                ""
            ])
        
        # Display summary text
        ax9.text(0.05, 0.95, '\n'.join(summary_text), 
                transform=ax9.transAxes, fontsize=10, 
                verticalalignment='top', fontfamily='monospace')
        
        plt.tight_layout()
        
        # Save the comprehensive dashboard
        output_file = self.output_dir / "comprehensive_trajectory_analysis_dashboard.png"
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"💾 Comprehensive dashboard saved: {output_file}")
        plt.close()
    
    def generate_comprehensive_report(self, data, quality_df):
        """Generate the final comprehensive report"""
        print("📄 Generating comprehensive analysis report...")
        
        report_lines = [
            "COMPREHENSIVE TRAJECTORY COMPLETENESS ANALYSIS REPORT",
            "=" * 60,
            f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "EXECUTIVE SUMMARY",
            "-" * 20
        ]
        
        # Executive summary
        if 'analysis' in data:
            analysis = data['analysis']
            
            if 'basic' in analysis:
                basic = analysis['basic']
                short_pct = basic['short_percentage']
                
                if short_pct < 1:
                    concern_level = "LOW"
                elif short_pct < 5:
                    concern_level = "MODERATE"
                else:
                    concern_level = "HIGH"
                
                report_lines.extend([
                    f"• Dataset contains {basic['total_trajectories']:,} trajectories",
                    f"• Short trajectory concern level: {concern_level} ({short_pct:.1f}% < 1000 points)",
                    f"• Average trajectory: {basic['avg_points']:.0f} points, {basic['avg_duration']:.2f} hours"
                ])
            
            if 'matching' in analysis:
                matching = analysis['matching']
                match_rate = matching['total_matched_trajectories'] / basic['total_trajectories'] * 100
                report_lines.extend([
                    f"• Official data matching rate: {match_rate:.1f}%",
                    f"• Duration consistency rate: {matching.get('consistency_rate', 0):.1f}%"
                ])
            
            if 'airport' in analysis:
                airport = analysis['airport']
                both_near_pct = airport['both_near_airports'] / airport['total_analyzed'] * 100
                report_lines.extend([
                    f"• Trajectories near both airports: {both_near_pct:.1f}%",
                    f"• Average distance to airports: {(airport['avg_start_distance'] + airport['avg_end_distance'])/2:.0f} km"
                ])
        
        if not quality_df.empty:
            excellent_pct = (quality_df['quality_class'] == 'Excellent').mean() * 100
            good_pct = (quality_df['quality_class'] == 'Good').mean() * 100
            high_quality_pct = excellent_pct + good_pct
            
            report_lines.extend([
                f"• High quality trajectories (Excellent + Good): {high_quality_pct:.1f}%",
                ""
            ])
        
        # Detailed analysis sections
        report_lines.extend([
            "1. TRAJECTORY LENGTH AND DURATION ANALYSIS",
            "-" * 45
        ])
        
        if 'basic' in data.get('analysis', {}):
            basic = data['analysis']['basic']
            report_lines.extend([
                f"Total trajectories: {basic['total_trajectories']:,}",
                f"Short trajectories (<1000 points): {basic['short_trajectories']:,} ({basic['short_percentage']:.2f}%)",
                "",
                "Statistical Summary:",
                f"  Point count - Mean: {basic['avg_points']:.0f}, Median: {basic['median_points']:.0f}",
                f"  Duration - Mean: {basic['avg_duration']:.2f}h, Median: {basic['median_duration']:.2f}h",
                ""
            ])
        
        report_lines.extend([
            "2. OFFICIAL FLIGHT DATA MATCHING",
            "-" * 35
        ])
        
        if 'matching' in data.get('analysis', {}):
            matching = data['analysis']['matching']
            report_lines.extend([
                f"Challenge set matches: {matching['challenge_set_matched']:,}",
                f"Submission set matches: {matching['submission_set_matched']:,}",
                f"Final submission matches: {matching['final_submission_matched']:,}",
                f"Total unique matches: {matching['total_matched_trajectories']:,}",
                ""
            ])
            
            if 'consistency_rate' in matching:
                report_lines.extend([
                    "Duration Consistency Analysis:",
                    f"  Trajectories with consistent duration (±10%): {matching['consistency_rate']:.1f}%",
                    f"  This indicates the quality of trajectory completeness",
                    ""
                ])
        
        report_lines.extend([
            "3. AIRPORT PROXIMITY ANALYSIS",
            "-" * 30
        ])
        
        if 'airport' in data.get('analysis', {}):
            airport = data['analysis']['airport']
            start_pct = airport['near_start_airport'] / airport['total_analyzed'] * 100
            end_pct = airport['near_end_airport'] / airport['total_analyzed'] * 100
            both_pct = airport['both_near_airports'] / airport['total_analyzed'] * 100
            
            report_lines.extend([
                f"Trajectories starting near airports (≤50km): {airport['near_start_airport']:,} ({start_pct:.1f}%)",
                f"Trajectories ending near airports (≤50km): {airport['near_end_airport']:,} ({end_pct:.1f}%)",
                f"Trajectories with both endpoints near airports: {airport['both_near_airports']:,} ({both_pct:.1f}%)",
                "",
                f"Average distance to nearest airport:",
                f"  Start points: {airport['avg_start_distance']:.0f} km",
                f"  End points: {airport['avg_end_distance']:.0f} km",
                ""
            ])
        
        report_lines.extend([
            "4. COMPREHENSIVE QUALITY CLASSIFICATION",
            "-" * 42
        ])
        
        if not quality_df.empty:
            quality_summary = quality_df['quality_class'].value_counts()
            total = len(quality_df)
            
            for quality, count in quality_summary.items():
                percentage = count / total * 100
                report_lines.append(f"{quality}: {count:,} ({percentage:.1f}%)")
            
            report_lines.extend([
                "",
                "Quality Classification Criteria:",
                "  Excellent (8-10 points): High point count + Long duration + Official match + Near airports",
                "  Good (6-7 points): Good point count + Reasonable duration + Some validation",
                "  Fair (4-5 points): Moderate quality with some concerns",
                "  Poor (0-3 points): Short trajectories with limited validation",
                ""
            ])
        
        # Conclusions and recommendations
        report_lines.extend([
            "5. CONCLUSIONS AND RECOMMENDATIONS",
            "-" * 38,
            ""
        ])
        
        # Determine overall assessment
        if 'analysis' in data:
            short_pct = data['analysis'].get('basic', {}).get('short_percentage', 0)
            match_rate = 0
            if 'matching' in data['analysis'] and 'basic' in data['analysis']:
                match_rate = data['analysis']['matching']['total_matched_trajectories'] / data['analysis']['basic']['total_trajectories'] * 100
            
            if not quality_df.empty:
                high_quality_pct = ((quality_df['quality_class'] == 'Excellent') | 
                                  (quality_df['quality_class'] == 'Good')).mean() * 100
            else:
                high_quality_pct = 0
            
            # Overall assessment
            if short_pct < 1 and match_rate > 50 and high_quality_pct > 30:
                assessment = "GOOD"
            elif short_pct < 5 and match_rate > 30:
                assessment = "MODERATE"
            else:
                assessment = "CONCERNING"
            
            report_lines.extend([
                f"Overall Data Quality Assessment: {assessment}",
                "",
                "Key Findings:",
                f"• {short_pct:.1f}% of trajectories are unusually short (<1000 points)",
                f"• {match_rate:.1f}% of trajectories match official flight records",
                f"• {high_quality_pct:.1f}% of trajectories meet high quality standards",
                ""
            ])
        
        # Specific recommendations
        report_lines.extend([
            "Recommendations for Data Usage:",
            "",
            "1. FOR HIGH-QUALITY ANALYSIS:",
            "   • Use only 'Excellent' and 'Good' quality trajectories",
            "   • Focus on trajectories that match official flight data",
            "   • Prioritize trajectories with both endpoints near airports",
            "",
            "2. FOR TRAJECTORY FILTERING:",
            "   • Apply minimum point count threshold (≥1000 points recommended)",
            "   • Apply minimum duration threshold (≥0.5 hours recommended)",
            "   • Consider airport proximity requirements based on research needs",
            "",
            "3. FOR COMPLETENESS VALIDATION:",
            "   • Cross-reference with official flight schedules when possible",
            "   • Validate altitude patterns for takeoff/landing detection",
            "   • Check geographic coverage against expected flight routes",
            "",
            "4. FOR RESEARCH APPLICATIONS:",
            "   • Document data quality criteria used in analysis",
            "   • Report percentage of data meeting quality thresholds",
            "   • Consider impact of incomplete trajectories on research conclusions"
        ])
        
        # Save comprehensive report
        report_file = self.output_dir / "comprehensive_trajectory_completeness_report.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_lines))
        
        print(f"📄 Comprehensive report saved: {report_file}")
        
        # Also save quality classification data
        if not quality_df.empty:
            quality_file = self.output_dir / "trajectory_quality_classification.parquet"
            quality_df.to_parquet(quality_file, index=False)
            print(f"💾 Quality classification data saved: {quality_file}")
            
            # Save high-quality trajectory IDs
            excellent_ids = quality_df[quality_df['quality_class'] == 'Excellent']['flight_id'].astype(str).tolist()
            good_ids = quality_df[quality_df['quality_class'] == 'Good']['flight_id'].astype(str).tolist()
            
            excellent_file = self.output_dir / "excellent_quality_trajectory_ids.txt"
            with open(excellent_file, 'w') as f:
                f.write('\n'.join(excellent_ids))
            print(f"📝 Saved {len(excellent_ids)} excellent quality trajectory IDs: {excellent_file}")
            
            good_file = self.output_dir / "good_quality_trajectory_ids.txt"
            with open(good_file, 'w') as f:
                f.write('\n'.join(good_ids))
            print(f"📝 Saved {len(good_ids)} good quality trajectory IDs: {good_file}")

def main():
    print("🚀 Comprehensive Trajectory Completeness Analysis Report")
    print("=" * 65)
    
    # Initialize report generator
    generator = ComprehensiveReportGenerator()
    
    # Load all analysis data
    data = generator.load_all_data()
    
    if not data:
        print("❌ No analysis data found! Please run the individual analysis scripts first.")
        return
    
    # Analyze overall trajectory quality
    data['analysis'] = generator.analyze_trajectory_quality(data)
    
    # Create comprehensive quality classification
    quality_df = generator.create_quality_classification(data)
    
    # Create comprehensive visualization
    generator.create_comprehensive_visualization(data, quality_df)
    
    # Generate comprehensive report
    generator.generate_comprehensive_report(data, quality_df)
    
    print("=" * 65)
    print("🎉 Comprehensive analysis report completed!")
    print(f"📁 Results saved to: {generator.output_dir.absolute()}")

if __name__ == "__main__":
    main()